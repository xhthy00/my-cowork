---
name: wechat-viral-radar
description: Search and analyze public WeChat Official Account article signals for recent viral topics, suspected 100k+ articles, track-by-track hot themes, title patterns, competitor monitoring seeds, manual fallback query packs, no-code chat workflows, and article idea reports. Use when the user asks for 微信公众号爆文, 10万+文章, 公众号赛道热点, 总榜热点, 选题库, 标题拆解, 竞品公众号观察, or public-source WeChat content research.
metadata:
  short-description: 微信公众号公开爆文与热点雷达
---

# WeChat Viral Radar

Use this skill to find public WeChat Official Account hot-article signals and turn them into an actionable content report.

## Quick Start

Choose the path that fits the user:

- **Chat-only mode**: use when the user wants results directly in the conversation or cannot run Python. Follow `references/chat_only_workflow.md`.
- **Script mode**: use when local execution is available and the user wants Markdown/CSV/JSON files.
- **Manual fallback mode**: use when public search is blocked or results are too thin. Use the generated `manual_fallback_queries.csv` or the query patterns in `references/public_sources.md`.

Common script commands:

```powershell
python scripts/start.py --track all --limit 10 --report-style deep
python scripts/start.py --track ai --freshness 7d --limit 10 --ideas-per-article 3
python scripts/start.py --mode hotlist --track all --freshness today --limit 12
python scripts/start.py --track career --keywords "副业,失业,普通人" --limit 10
```

## When To Use

Use this skill when the user says things like:

- "帮我找公众号最近 10 万+ 爆文"
- "看看公众号总榜热点"
- "找 AI / 财经 / 情感 / 教育赛道的爆款标题"
- "拆一下这些公众号爆文为什么火"
- "给我生成今天公众号选题"
- "监控几个竞品公众号的公开文章方向"

## Input Parameters

See `references/parameters.md` for full parameter descriptions and examples.

Core options:

- `track`: `all`, `ai`, `finance`, `emotion`, `education`, `career`, or another built-in track.
- `freshness`: `today`, `7d`, or `30d`.
- `mode`: `articles` or `hotlist`.
- `report-style`: `concise` or `deep`.
- `keywords`: extra niche terms.
- `limit`: maximum article candidates.

## Output Shape

A complete report should include:

- insight summary
- top topics
- article candidates
- signal level and confidence
- title formulas
- audience pain points
- creative angle bank
- original writing ideas
- 3-day publishing plan
- risk notes
- source warnings
- manual fallback queries

If no live articles are collected, still produce a useful fallback report with query links, troubleshooting steps, and the next best manual action.

## Important Boundaries

- This free public version uses public web/search signals only. It cannot guarantee full coverage of all WeChat articles.
- Public pages usually show `10万+` instead of exact read counts. Treat results as `confirmed_100k_public`, `suspected_viral`, or `topic_candidate`.
- If a public source shows captcha, throttling, expired links, or no parseable results, the script retries and still produces a fallback query pack.
- Do not scrape private dashboards, bypass login, or ignore a platform's access rules.
- Paid rankings, exact read counts, low-follower viral lists, and long-term dashboard monitoring are enhanced-source features for a later version.

## Track Names

Built-in track names are defined in `references/tracks.json`.

Common tracks:

- `ai`
- `business`
- `finance`
- `emotion`
- `career`
- `education`
- `health`
- `parenting`
- `local_life`
- `culture`
- `entertainment`
- `auto`
- `real_estate`
- `all`

If the user gives a custom track, map it to the closest built-in track and add the user's terms as extra keywords.

## Signal Labels

- `confirmed_100k_public`: the title/snippet/page explicitly includes `10万+`, `100000+`, `10w+`, or `十万+`.
- `suspected_viral`: public search result has strong hot-topic/title signals but no visible read-count proof.
- `topic_candidate`: useful for trend research but not enough evidence to call viral.
- `source_warning`: source access, parsing, or throttling issue; use the fallback query pack.

Use cautious wording. Prefer "公开信号显示" or "疑似爆款候选" unless the public page visibly confirms `10万+`.

## Public Source Strategy

Start with these public paths:

- Sogou Weixin public article search.
- General web search with `微信公众号 10万+ 爆文` plus track keywords.
- Public list pages or articles from Newrank, Qingbo, Xigua Data, Yiban, and similar platforms, when visible without login.

If live public search is weak or blocked:

1. Check the `Source Warnings` section.
2. Open `manual_fallback_queries.csv`.
3. Try the generated Sogou Weixin and general web queries manually.
4. Paste any found article links back into the conversation for analysis.

## FAQ And Examples

- Read `references/faq.md` when the user asks about reliability, exact read counts, paid tools, installation issues, or risk boundaries.
- Read `examples/workflows.md` for common workflows.
- Read `examples/full_report_sample.md` to see a complete final-report shape.

## Useful Scripts

- `scripts/start.py`: main CLI wrapper.
- `scripts/wechat_viral_radar.py`: public search, retry, fallback query pack, scoring, and report generation.
- `scripts/doctor.py`: environment check.
- `scripts/verify_package.py`: package validation, demo run, fallback-mode run, and deep-report check.

Read script help with:

```powershell
python scripts/start.py --help
```

