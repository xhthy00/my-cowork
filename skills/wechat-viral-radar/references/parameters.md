# Parameters

Use this file when the user asks what to enter, how to narrow the search, or why a command returned weak results.

## Core Parameters

| Parameter | Values | Default | Use When |
|---|---|---:|---|
| `--track` | `all`, `ai`, `finance`, `emotion`, `career`, etc. | `all` | Pick a content track or use `all` for broad discovery. |
| `--mode` | `articles`, `hotlist` | `articles` | Use `hotlist` for topic discovery; use `articles` for article candidates. |
| `--freshness` | `today`, `7d`, `30d` | `7d` | Controls query wording for recency. |
| `--keywords` | comma/space separated terms | empty | Add a niche, city, person, brand, or trend. |
| `--limit` | integer | `12` | Maximum candidates in the report. |
| `--report-style` | `concise`, `deep` | `deep` | `deep` adds angle bank, publishing plan, and audience insights. |
| `--ideas-per-article` | integer | `2` | Number of original idea variants per article. |
| `--retries` | integer | `2` | Retry public-source requests. |
| `--timeout` | seconds | `12` | Timeout per public-source request. |
| `--demo` | flag | off | Generate sample output without network. |
| `--simulate-blocked` | flag | off | Verify fallback reporting when live search fails. |

## Good Defaults

- Broad public radar: `--track all --mode hotlist --freshness today --limit 12 --report-style deep`
- Single track: `--track ai --freshness 7d --limit 10 --ideas-per-article 3`
- Narrow niche: `--track all --keywords "银发经济,养老金,退休生活" --limit 10`
- Unstable network: `--track finance --limit 6 --retries 1 --timeout 8`

## How To Improve Results

- Too broad: add 2-4 specific keywords.
- Too few results: change `today` to `7d` or `30d`.
- Too many tool/tutorial results: add audience keywords such as `家长`, `老板`, `普通人`, `女性`, or `打工人`.
- Need exact ranking: use enhanced sources such as Newrank, Qingbo, Xigua Data, or a user-provided export.

