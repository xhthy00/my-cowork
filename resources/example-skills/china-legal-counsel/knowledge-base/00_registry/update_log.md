# Legal Counsel KB Update Log

## 2026-05-08

- Created initial knowledge base folder structure.
- Added first source registry, core law targets, and crawl policy.
- Added direct official source seeds for `生成式人工智能服务管理暂行办法` and `人工智能生成合成内容标识办法`.
- Fetched both official pages into `01_raw/official_laws/`.
- Normalized them into `02_clean/markdown/` and `02_clean/json/`.
- Chunked them by article into `03_chunks/laws_by_article/` (24 chunks and 14 chunks respectively, plus chunk manifests).

## 2026-05-08 23:00 CST

- Embedded the knowledge base into the skill at `knowledge-base/` so the skill is self-contained.
- Expanded `sources.yaml` to 42 registered sources: 36 P0/P1 official or quasi-official sources plus licensed/commentary placeholders.
- Added and fetched a first official-law batch covering civil law, company law, contract judicial interpretation, data/privacy/AI, advertising, IP, consumer protection, and online competition.
- Stored raw official materials in `01_raw/`, normalized text/metadata in `02_clean/`, and regenerated article-level chunks in `03_chunks/laws_by_article/`.
- Updated fetcher fallback for National Laws Database PDFs and chunking regex for PDF-extracted article headings with leading whitespace.
