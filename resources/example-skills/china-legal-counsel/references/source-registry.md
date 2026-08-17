# Source Registry

Use this reference when collecting, ranking, or updating legal sources for the local knowledge base.

## Default KB Location

Bundled path inside this skill: `knowledge-base/` (relative to this skill's Base directory).

Run scripts from the skill root; do not hard-code Codex/home absolute paths.

## Source Priority

1. Official laws and regulations: 国家法律法规数据库, 中国人大网, 中国政府网, 司法部行政法规库.
2. Judicial sources: 最高人民法院, 人民法院案例库, 指导性案例, 最高人民法院知识产权法庭, 中国裁判文书网.
3. Regulators: 网信办, 市场监管总局, 工信部, 人社部, 国家知识产权局, 药监局, 金融监管总局, 证监会, 税务总局.
4. Official templates and standards: 国家市场监管总局合同示范文本库, 国家标准全文公开系统.
5. Local sources: 杭州互联网法院, 杭州仲裁委, 浙江法院网, 杭州市市场监管局.
6. Licensed commercial sources: 北大法宝, 威科先行, 法信, 法天使, CNKI/万方.
7. Practical commentary: top law-firm articles and reputable legal media; use as playbook material, not final authority.

## Capture Policy

- Full-text official public sources may be saved and indexed with source URL, fetch date, checksum, and status.
- Paid or licensed databases may be indexed only within the license scope. Do not bulk-copy full text without authorization.
- Law-firm/media articles should usually be stored as title, URL, date, summary, tags, and human notes unless permission allows full text.
- Keep old versions. Historical disputes may require the law effective at the time of the event.

## Registry Fields

Use `00_registry/sources.yaml` with:

- `id`
- `name`
- `url`
- `authority_level`: P0/P1/P2/P3
- `source_type`: official_law, official_case, judicial_interpretation, regulator, template, standard, licensed_database, commentary
- `jurisdiction`
- `auth_required`
- `full_text_allowed`
- `fetch_method`
- `update_frequency`
- `parser`
- `notes`

## P0 Source Starters

- 国家法律法规数据库: https://flk.npc.gov.cn/
- 中国政府网政策库: https://www.gov.cn/zhengce/
- 最高人民法院: https://www.court.gov.cn/
- 人民法院案例库: https://rmfyalk.court.gov.cn/
- 中国裁判文书网: https://wenshu.court.gov.cn/
- 国家市场监管总局合同示范文本库: https://htsfwb.samr.gov.cn/
- 国家网信办: https://www.cac.gov.cn/
- 市场监管总局: https://www.samr.gov.cn/
- 国家知识产权局: https://www.cnipa.gov.cn/
