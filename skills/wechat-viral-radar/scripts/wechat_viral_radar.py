import argparse
import csv
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "reports"
TRACKS_PATH = ROOT / "references" / "tracks.json"


HOT_WORDS = [
    "刚刚", "突然", "最新", "重磅", "爆了", "刷屏", "热搜", "全网", "官方",
    "通报", "宣布", "首次", "罕见", "彻底", "终于", "真相", "普通人", "打工人",
    "崩了", "涨了", "跌了", "改变", "机会", "警惕", "避坑", "后悔", "看哭",
]

RISK_WORDS = [
    "稳赚", "暴富", "包治", "根治", "偏方", "内幕消息", "荐股", "保本",
    "诊断", "处方", "政治", "敏感", "搬运", "洗稿",
]


class SourceBlocked(RuntimeError):
    pass


@dataclass
class ArticleCandidate:
    title: str
    account: str = ""
    date: str = ""
    url: str = ""
    snippet: str = ""
    track: str = ""
    track_label: str = ""
    query: str = ""
    source: str = "sogou_weixin"
    signal: str = "topic_candidate"
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


@dataclass
class ManualQuery:
    track: str
    track_label: str
    query: str
    sogou_url: str
    web_query: str


def load_tracks() -> dict:
    if TRACKS_PATH.exists():
        return json.loads(TRACKS_PATH.read_text(encoding="utf-8"))
    return {}


def strip_tags(value: str) -> str:
    value = re.sub(r"<script[\s\S]*?</script>", " ", value, flags=re.I)
    value = re.sub(r"<style[\s\S]*?</style>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def fetch_url(url: str, timeout: int = 12, retries: int = 2, backoff: float = 1.2) -> str:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WeChatViralRadar/1.0",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
                page = raw.decode(charset, errors="replace")
                if re.search(r"验证码|请输入验证码|antispider|访问过于频繁|用户您好", page, flags=re.I):
                    raise SourceBlocked("public source returned captcha or throttling page")
                return page
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
    raise last_error or RuntimeError("unknown source error")


def normalize_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return "https://weixin.sogou.com" + url
    return url


def parse_sogou_results(page: str, track: str, track_label: str, query: str) -> list[ArticleCandidate]:
    items: list[ArticleCandidate] = []
    blocks = re.findall(r'<div class="txt-box">([\s\S]*?)(?=<div class="txt-box">|</body>)', page)
    if not blocks:
        blocks = re.findall(r'<li[^>]*>([\s\S]*?</li>)', page)

    for block in blocks:
        title_match = re.search(r"<h3[^>]*>\s*<a[^>]*href=\"([^\"]+)\"[^>]*>([\s\S]*?)</a>", block)
        if not title_match:
            title_match = re.search(r"<a[^>]*href=\"([^\"]+)\"[^>]*>([\s\S]*?)</a>", block)
        if not title_match:
            continue

        url = normalize_url(html.unescape(title_match.group(1)))
        title = strip_tags(title_match.group(2))
        if not title or len(title) < 4:
            continue

        snippet = ""
        snippet_match = re.search(r'<p class="txt-info"[^>]*>([\s\S]*?)</p>', block)
        if snippet_match:
            snippet = strip_tags(snippet_match.group(1))

        account = ""
        account_match = re.search(r'class="account"[^>]*>([\s\S]*?)</a>', block)
        if account_match:
            account = strip_tags(account_match.group(1))

        date = ""
        date_match = re.search(r'class="s2"[^>]*>([\s\S]*?)</span>', block)
        if date_match:
            date = strip_tags(date_match.group(1))

        items.append(
            ArticleCandidate(
                title=title,
                account=account,
                date=date,
                url=url,
                snippet=snippet,
                track=track,
                track_label=track_label,
                query=query,
            )
        )
    return dedupe(items)


def dedupe(items: Iterable[ArticleCandidate]) -> list[ArticleCandidate]:
    seen: set[str] = set()
    output: list[ArticleCandidate] = []
    for item in items:
        key = re.sub(r"\W+", "", item.title.lower())[:60] or item.url
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def score_candidate(item: ArticleCandidate) -> ArticleCandidate:
    text = f"{item.title} {item.snippet}"
    score = 20
    reasons: list[str] = []

    if re.search(r"(10\s*万\+|10\s*w\+|100000\+|十万\+)", text, flags=re.I):
        score += 55
        item.signal = "confirmed_100k_public"
        reasons.append("public text contains 100k+ signal")
    else:
        item.signal = "topic_candidate"

    for word in HOT_WORDS:
        if word in text:
            score += 5
            reasons.append(f"hot word: {word}")

    if item.date:
        score += 6
        reasons.append("has public date")

    if item.account:
        score += 4
        reasons.append("has account name")

    title_len = len(item.title)
    if 12 <= title_len <= 32:
        score += 5
        reasons.append("compact title length")
    elif title_len > 45:
        score -= 4

    risks = [word for word in RISK_WORDS if word in text]
    if risks:
        score -= 8
        reasons.append("risk-sensitive wording")

    if item.signal != "confirmed_100k_public" and score >= 50:
        item.signal = "suspected_viral"

    item.score = max(0, min(score, 100))
    item.reasons = reasons[:6]
    item.risks = risks
    return item


def freshness_terms(freshness: str) -> list[str]:
    if freshness == "today":
        return ["今天", "最新"]
    if freshness == "7d":
        return ["最近", "本周"]
    if freshness == "30d":
        return ["近30天", "最近"]
    return ["最新"]


def build_queries(track: str, tracks: dict, extra_keywords: list[str], mode: str, freshness: str) -> list[tuple[str, str, str]]:
    if track == "all":
        selected = list(tracks.items())
    elif track in tracks:
        selected = [(track, tracks[track])]
    else:
        selected = [(track, {"label": track, "keywords": [track]})]

    queries: list[tuple[str, str, str]] = []
    terms = freshness_terms(freshness)
    for key, info in selected:
        label = info.get("label", key)
        words = list(info.get("keywords", []))
        if extra_keywords:
            words.extend(extra_keywords)
        words = words[:4] if mode != "hotlist" else words[:3]
        for word in words:
            if mode == "hotlist":
                query = f"微信公众号 热点 10万+ {terms[0]} {word}"
            else:
                query = f"{word} 公众号 10万+ 爆文 {terms[0]}"
            queries.append((key, label, query))
    return queries


def make_manual_queries(query_rows: list[tuple[str, str, str]]) -> list[ManualQuery]:
    manual: list[ManualQuery] = []
    for key, label, query in query_rows:
        encoded = urllib.parse.urlencode({"type": "2", "query": query})
        sogou_url = f"https://weixin.sogou.com/weixin?{encoded}"
        web_query = f"{query} site:mp.weixin.qq.com OR 新榜 OR 清博 OR 西瓜数据"
        manual.append(ManualQuery(key, label, query, sogou_url, web_query))
    return manual


def source_warning(track: str, label: str, query: str, message: str) -> ArticleCandidate:
    return ArticleCandidate(
        title=f"Source warning for query: {query}",
        track=track,
        track_label=label,
        query=query,
        source="sogou_weixin",
        signal="source_warning",
        score=0,
        reasons=[message, "Use manual_fallback_queries.csv or retry with narrower keywords."],
    )


def search_sogou(
    track: str,
    tracks: dict,
    extra_keywords: list[str],
    limit: int,
    mode: str,
    freshness: str,
    retries: int,
    timeout: int,
    simulate_blocked: bool,
) -> tuple[list[ArticleCandidate], list[ManualQuery]]:
    candidates: list[ArticleCandidate] = []
    query_rows = build_queries(track, tracks, extra_keywords, mode, freshness)
    manual_queries = make_manual_queries(query_rows)

    for key, label, query in query_rows:
        encoded = urllib.parse.urlencode({"type": "2", "query": query})
        url = f"https://weixin.sogou.com/weixin?{encoded}"
        try:
            if simulate_blocked:
                raise SourceBlocked("simulated source block for reliability testing")
            page = fetch_url(url, timeout=timeout, retries=retries)
            parsed = parse_sogou_results(page, key, label, query)
            if parsed:
                candidates.extend(parsed)
            else:
                candidates.append(source_warning(key, label, query, "No parseable public results returned."))
        except Exception as exc:
            candidates.append(source_warning(key, label, query, f"{type(exc).__name__}: {exc}"))
        time.sleep(0.8)
        if len([c for c in candidates if c.signal != "source_warning"]) >= limit * 2:
            break

    scored = [score_candidate(item) for item in candidates if item.signal != "source_warning"]
    warnings = [item for item in candidates if item.signal == "source_warning"]
    return sorted(scored, key=lambda item: item.score, reverse=True)[:limit] + warnings[:5], manual_queries[:20]


def demo_candidates(track: str, tracks: dict, limit: int, mode: str, freshness: str) -> tuple[list[ArticleCandidate], list[ManualQuery]]:
    samples = [
        ArticleCandidate(
            title="刚刚，AI Agent 又把打工人的一天改了，阅读 10万+",
            account="示例科技号",
            date="2026-06-18",
            url="https://example.com/ai-agent",
            snippet="公开示例：AI Agent、效率工具、普通人使用场景正在形成传播热点。",
            track="ai",
            track_label="AI / 科技",
            query="AI Agent 公众号 10万+ 爆文",
        ),
        ArticleCandidate(
            title="今年最适合普通人的副业，不是开店",
            account="示例职场号",
            date="2026-06-17",
            url="https://example.com/side-hustle",
            snippet="副业、失业焦虑、普通人可复制路径。",
            track="career",
            track_label="职场 / 副业",
            query="副业 公众号 10万+ 爆文",
        ),
        ArticleCandidate(
            title="高考志愿填报前，家长最容易忽略的 3 件事",
            account="示例教育号",
            date="2026-06-16",
            url="https://example.com/gaokao",
            snippet="季节性教育热点，决策焦虑强。",
            track="education",
            track_label="教育 / 学习",
            query="高考 公众号 10万+ 爆文",
        ),
        ArticleCandidate(
            title="楼市突然变了，普通家庭要先看懂这件事",
            account="示例房产号",
            date="2026-06-15",
            url="https://example.com/house",
            snippet="政策变化、家庭资产、买房决策。",
            track="real_estate",
            track_label="房产",
            query="楼市 公众号 10万+ 爆文",
        ),
    ]
    if track != "all":
        samples = [item for item in samples if item.track == track] or samples[:2]
    query_rows = build_queries(track, tracks, [], mode, freshness)
    return [score_candidate(item) for item in samples[:limit]], make_manual_queries(query_rows)[:12]


def extract_topics(items: list[ArticleCandidate]) -> list[tuple[str, int, str]]:
    topic_scores: dict[str, int] = {}
    topic_reasons: dict[str, str] = {}
    for item in items:
        text = f"{item.title} {item.snippet}"
        words = re.findall(r"[A-Za-z][A-Za-z0-9+\-.]{1,}|[\u4e00-\u9fff]{2,6}", text)
        for word in words:
            if word in {"公众号", "爆文", "阅读", "示例", "公开", "文章", "最近"}:
                continue
            gain = 2 + item.score // 20
            if word in HOT_WORDS:
                gain += 3
            topic_scores[word] = topic_scores.get(word, 0) + gain
            topic_reasons[word] = f"appears in high-scoring {item.track_label or item.track} candidates"
    ranked = sorted(topic_scores.items(), key=lambda kv: kv[1], reverse=True)[:12]
    return [(word, score, topic_reasons.get(word, "")) for word, score in ranked]


def title_formula(title: str) -> str:
    if re.search(r"刚刚|突然|最新|重磅", title):
        return "时间钩子 + 强变化 + 受影响人群"
    if re.search(r"不是|而是|真相|其实", title):
        return "反常识判断 + 新解释"
    if re.search(r"\d+|三|五|十", title):
        return "高压场景 + 数字化清单"
    if re.search(r"普通人|打工人|家长|老板|女性", title):
        return "明确人群 + 痛点/机会"
    return "热点对象 + 情绪结果/行动建议"


def idea_from_item(item: ArticleCandidate) -> str:
    audience = "普通读者"
    if "家长" in item.title or item.track == "education":
        audience = "家长"
    elif "打工人" in item.title or item.track == "career":
        audience = "职场人"
    elif item.track == "ai":
        audience = "普通创作者和小老板"
    elif item.track == "finance":
        audience = "普通家庭"

    core = re.sub(r"[，。！？!?,].*$", "", item.title)
    core = re.sub(r"(阅读\s*)?10\s*(万|w)\+", "", core, flags=re.I)
    return f"面向{audience}重写：{core}背后的 3 个机会和 2 个误区"


def confidence_label(item: ArticleCandidate) -> str:
    if item.signal == "confirmed_100k_public":
        return "High: public 100k+ signal is visible"
    if item.signal == "suspected_viral":
        return "Medium: strong title/topic signal, no visible read-count proof"
    if item.signal == "topic_candidate":
        return "Low: useful trend candidate, needs manual validation"
    return "Source issue: use fallback query"


def audience_for_item(item: ArticleCandidate) -> str:
    title = item.title
    if item.track == "education" or "家长" in title or "高考" in title:
        return "家长、学生、教育从业者"
    if item.track == "career" or "打工人" in title or "副业" in title:
        return "职场人、副业探索者、普通上班族"
    if item.track == "finance" or "楼市" in title or "基金" in title:
        return "普通家庭、投资新手、资产决策人群"
    if item.track == "ai":
        return "创作者、小老板、知识工作者"
    if item.track == "emotion":
        return "亲密关系和自我成长读者"
    return "对该话题有现实决策需求的普通读者"


def pain_point_for_item(item: ArticleCandidate) -> str:
    if item.track == "ai":
        return "怕错过新工具，也怕不知道怎么把工具变成实际效率。"
    if item.track == "career":
        return "担心收入不稳定，希望找到普通人可执行的替代路径。"
    if item.track == "education":
        return "决策时间短、信息过载，害怕因为不了解规则而吃亏。"
    if item.track == "finance":
        return "看不懂变化背后的影响，担心家庭资产做错决定。"
    if item.track == "health":
        return "想要确定答案，但容易被夸张说法和伪科普影响。"
    return "想快速判断这件事和自己有什么关系，以及下一步该怎么做。"


def creative_angles(item: ArticleCandidate) -> list[str]:
    core = re.sub(r"[，。！？!?,].*$", "", item.title)
    core = re.sub(r"(阅读\s*)?10\s*(万|w)\+", "", core, flags=re.I).strip(" ：:")
    if not core:
        core = item.track_label or item.track or "这个热点"
    return [
        f"普通人视角：{core}，真正影响普通人的地方是什么？",
        f"误区拆解：关于{core}，多数人容易误判的 3 件事",
        f"行动清单：如果你也关注{core}，今天可以先做哪 5 步",
    ]


def publishing_plan(items: list[ArticleCandidate]) -> list[tuple[str, str, str, str]]:
    if not items:
        return [
            ("Day 1", "热点搜索", "先用 fallback queries 收集 5 条公开链接", "补足证据"),
            ("Day 2", "标题拆解", "从找到的标题里提炼 3 个模板", "形成可写角度"),
            ("Day 3", "原创文章", "选择一个普通人场景写成清单文", "发布测试"),
        ]
    top = items[0]
    second = items[1] if len(items) > 1 else top
    third = items[2] if len(items) > 2 else top
    return [
        ("Day 1", "热点解释", f"围绕《{top.title}》写发生了什么和影响谁", "抢及时性"),
        ("Day 2", "实用清单", f"围绕《{second.title}》写普通人可执行步骤", "提高收藏"),
        ("Day 3", "观点拆解", f"围绕《{third.title}》写反常识判断和误区", "建立观点"),
    ]


def write_outputs(
    items: list[ArticleCandidate],
    manual_queries: list[ManualQuery],
    output_dir: Path,
    mode: str,
    freshness: str,
    report_style: str,
    ideas_per_article: int,
) -> tuple[Path, Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "wechat_viral_report.md"
    csv_path = output_dir / "wechat_viral_articles.csv"
    json_path = output_dir / "wechat_viral_articles.json"
    fallback_path = output_dir / "manual_fallback_queries.csv"

    valid_items = [item for item in items if item.signal != "source_warning"]
    topics = extract_topics(valid_items)

    lines = [
        "# 微信公众号爆款雷达报告",
        "",
        f"- Mode: `{mode}`",
        f"- Freshness: `{freshness}`",
        f"- Report style: `{report_style}`",
        "- Source type: free public signals",
        "- Note: 公开版只能确认可见的 `10万+` 信号；无可见阅读量时按疑似爆款/热点候选处理。",
        "",
        "## Insight Summary",
        "",
        f"- Collected article candidates: {len(valid_items)}",
        f"- Source warnings: {len([item for item in items if item.signal == 'source_warning'])}",
        "- Use confirmed signals for proof, suspected signals for inspiration, and fallback queries when public search is unstable.",
        "",
        "## Top Topics",
        "",
        "| Rank | Topic | Score | Why It Matters |",
        "|---:|---|---:|---|",
    ]
    if topics:
        for idx, (topic, score, reason) in enumerate(topics[:10], 1):
            lines.append(f"| {idx} | {topic} | {score} | {reason} |")
    else:
        lines.append("| 1 | No live topic collected | 0 | Use fallback queries or retry later. |")

    lines.extend([
        "",
        "## Article Candidates",
        "",
        "| Signal | Track | Title | Account | Date | Score | Link |",
        "|---|---|---|---|---|---:|---|",
    ])
    for item in items:
        link = item.url or ""
        safe_title = item.title.replace("|", "\\|")
        lines.append(
            f"| {item.signal} | {item.track_label or item.track} | {safe_title} | {item.account} | {item.date} | {item.score} | {link} |"
        )

    lines.extend(["", "## Confidence Notes", ""])
    lines.extend(["| Title | Confidence | Reason |", "|---|---|---|"])
    for item in items[:8]:
        safe_title = item.title.replace("|", "\\|")
        reason = "; ".join(item.reasons[:3]) if item.reasons else "No detailed reason available."
        lines.append(f"| {safe_title} | {confidence_label(item)} | {reason} |")

    lines.extend(["", "## Title Formulas", ""])
    if valid_items:
        for item in valid_items[:8]:
            lines.append(f"- `{title_formula(item.title)}`: {item.title}")
    else:
        lines.append("- No article candidates yet. Use the fallback queries below, then paste links back for title teardown.")

    lines.extend(["", "## Original Writing Ideas", ""])
    if valid_items:
        for item in valid_items[:8]:
            variants = [idea_from_item(item)] + creative_angles(item)
            for idea in variants[: max(1, ideas_per_article)]:
                lines.append(f"- {idea}")
    else:
        lines.append("- Pick one fallback query, collect 3-5 public article links, then generate original angles from their titles.")

    if report_style == "deep":
        lines.extend(["", "## Audience Pain Points", ""])
        lines.extend(["| Title | Audience | Pain Point |", "|---|---|---|"])
        for item in valid_items[:8]:
            safe_title = item.title.replace("|", "\\|")
            lines.append(f"| {safe_title} | {audience_for_item(item)} | {pain_point_for_item(item)} |")

        lines.extend(["", "## Creative Angle Bank", ""])
        if valid_items:
            for item in valid_items[:5]:
                lines.append(f"- Source: {item.title}")
                for angle in creative_angles(item):
                    lines.append(f"  - {angle}")
        else:
            lines.append("- Ordinary-person experiment: I tried this for 7 days.")
            lines.append("- Mistake teardown: most people misunderstand this point.")
            lines.append("- Decision checklist: before choosing, check these 5 things.")

        lines.extend(["", "## 3-Day Publishing Plan", ""])
        lines.extend(["| Day | Content Type | Title Direction | Goal |", "|---|---|---|---|"])
        for day, content_type, direction, goal in publishing_plan(valid_items):
            lines.append(f"| {day} | {content_type} | {direction} | {goal} |")

    lines.extend(["", "## Risk Notes", ""])
    risk_items = [item for item in valid_items if item.risks]
    if risk_items:
        for item in risk_items:
            lines.append(f"- {item.title}: watch {', '.join(item.risks)}")
    else:
        lines.append("- No obvious high-risk wording detected. Still review medical, finance, legal, and policy-sensitive topics manually.")

    lines.extend(["", "## Manual Fallback Queries", ""])
    lines.extend(["| Track | Query | Sogou Weixin URL | General Web Query |", "|---|---|---|---|"])
    for row in manual_queries[:10]:
        lines.append(f"| {row.track_label} | {row.query} | {row.sogou_url} | {row.web_query} |")

    lines.extend(["", "## Source Warnings", ""])
    warnings = [item for item in items if item.signal == "source_warning"]
    if warnings:
        for item in warnings:
            lines.append(f"- {item.title}: {'; '.join(item.reasons)}")
    else:
        lines.append("- No source warnings.")

    lines.extend([
        "",
        "## Troubleshooting",
        "",
        "- If results are empty, retry later or reduce `--limit`.",
        "- If a source is blocked, open `manual_fallback_queries.csv` and search manually.",
        "- If results are too broad, add `--keywords` with 2-4 concrete terms.",
        "- If exact rankings are required, use an enhanced source such as Newrank, Qingbo, or Xigua Data.",
    ])

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    with csv_path.open("w", newline="", encoding="utf-8-sig") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=["signal", "score", "track", "track_label", "title", "account", "date", "url", "query", "source", "reasons", "risks"],
        )
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "signal": item.signal,
                    "score": item.score,
                    "track": item.track,
                    "track_label": item.track_label,
                    "title": item.title,
                    "account": item.account,
                    "date": item.date,
                    "url": item.url,
                    "query": item.query,
                    "source": item.source,
                    "reasons": "; ".join(item.reasons),
                    "risks": "; ".join(item.risks),
                }
            )

    with fallback_path.open("w", newline="", encoding="utf-8-sig") as fp:
        writer = csv.DictWriter(fp, fieldnames=["track", "track_label", "query", "sogou_url", "web_query"])
        writer.writeheader()
        for row in manual_queries:
            writer.writerow(row.__dict__)

    json_path.write_text(
        json.dumps([item.__dict__ for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return md_path, csv_path, json_path, fallback_path


def parse_keywords(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in re.split(r"[,，;；\s]+", value) if part.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search public WeChat viral article signals and create a report.")
    parser.add_argument("--track", default="all", help="Track name, custom keyword, or all.")
    parser.add_argument("--keywords", default="", help="Extra comma/space separated keywords.")
    parser.add_argument("--limit", type=int, default=12, help="Maximum article candidates.")
    parser.add_argument("--mode", choices=["articles", "hotlist"], default="articles", help="Report mode.")
    parser.add_argument("--freshness", choices=["today", "7d", "30d"], default="7d", help="Freshness hint for public search queries.")
    parser.add_argument("--report-style", choices=["concise", "deep"], default="deep", help="Report depth. Deep adds audience insights, angle bank, and a publishing plan.")
    parser.add_argument("--ideas-per-article", type=int, default=2, help="Number of original idea variants per collected article.")
    parser.add_argument("--retries", type=int, default=2, help="Retry count for each public source request.")
    parser.add_argument("--timeout", type=int, default=12, help="Timeout seconds for each public source request.")
    parser.add_argument("--simulate-blocked", action="store_true", help="Simulate a blocked source and verify fallback report generation.")
    parser.add_argument("--demo", action="store_true", help="Use built-in demo records without network.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for Markdown/CSV/JSON outputs.")
    args = parser.parse_args(argv)

    tracks = load_tracks()
    extra_keywords = parse_keywords(args.keywords)
    if args.demo:
        items, manual_queries = demo_candidates(args.track, tracks, args.limit, args.mode, args.freshness)
    else:
        items, manual_queries = search_sogou(
            args.track,
            tracks,
            extra_keywords,
            args.limit,
            args.mode,
            args.freshness,
            args.retries,
            args.timeout,
            args.simulate_blocked,
        )
        if not [item for item in items if item.signal != "source_warning"]:
            print("No public results collected. A fallback query pack was generated.", file=sys.stderr)

    md_path, csv_path, json_path, fallback_path = write_outputs(
        items,
        manual_queries,
        Path(args.output_dir),
        args.mode,
        args.freshness,
        args.report_style,
        max(1, args.ideas_per_article),
    )
    print(f"Report: {md_path}")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    print(f"Fallback queries: {fallback_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
