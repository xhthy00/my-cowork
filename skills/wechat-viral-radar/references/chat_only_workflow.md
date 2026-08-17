# Chat-Only Workflow

Use this workflow when the user cannot run Python or wants the answer directly in chat.

## Step 1: Confirm Scope

Ask only if missing:

- track: all / AI / finance / emotion / education / career / custom
- freshness: today / 7 days / 30 days
- output: hotlist / article candidates / title teardown / writing ideas

If the user does not specify, default to:

- track: `all`
- freshness: `7d`
- output: hotlist + article candidates + ideas

## Step 2: Search Public Sources

Use public web search with queries like:

- `微信公众号 10万+ 爆文 <track keyword> 最新`
- `微信公众号 热点 10万+ <track keyword> 本周`
- `新榜 公众号 爆文 <track keyword>`
- `清博 公众号 榜单 <track keyword>`
- `西瓜数据 爆款素材库 公众号 <track keyword>`

Do not claim full coverage. Label each finding by evidence strength.

## Step 3: Classify Evidence

- `confirmed_100k_public`: visible `10万+`, `10w+`, `100000+`, or `十万+`.
- `suspected_viral`: strong public topic/title signal but no visible read-count proof.
- `topic_candidate`: useful trend but weak viral evidence.

## Step 4: Return This Report

1. Insight summary
2. Top topics
3. Article candidates with links
4. Title formulas
5. Audience pain points
6. Creative angle bank
7. Original writing ideas
8. Risk notes
9. What to search next

## Step 5: If Search Is Blocked

Return fallback queries instead of stopping. Tell the user which terms to open manually and ask them to paste back links/screenshots for deeper teardown.

