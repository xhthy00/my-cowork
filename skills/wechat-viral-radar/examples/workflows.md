# Example Workflows

## 1. Chat-Only: 全赛道热点

Use when the user cannot run scripts.

Prompt:

```text
帮我用公开信息查最近 7 天微信公众号全赛道热点，按 confirmed_100k_public / suspected_viral / topic_candidate 分类，输出热点、文章候选、标题公式、原创选题和风险提醒。
```

## 2. Script: 全赛道总榜热点

```powershell
python scripts/start.py --mode hotlist --track all --freshness today --limit 12 --report-style deep
```

Use when the user wants today's public hot topics across multiple WeChat tracks.

## 3. Script: 单赛道爆文候选

```powershell
python scripts/start.py --track ai --freshness 7d --limit 10 --ideas-per-article 3
```

Use when the user cares about one track and wants article candidates, title formulas, and writing ideas.

## 4. Script: 自定义关键词

```powershell
python scripts/start.py --track all --keywords "银发经济,养老金,退休生活" --limit 10 --report-style deep
```

Use when the user has a niche topic that is not fully covered by built-in tracks.

## 5. Script: 网络不稳定时

```powershell
python scripts/start.py --track finance --simulate-blocked --limit 5
```

This verifies that fallback query generation still works when live public search fails.

## 6. Manual Fallback

Open `manual_fallback_queries.csv`, search 3-5 generated queries manually, then paste article links back into the chat for deeper title teardown.

