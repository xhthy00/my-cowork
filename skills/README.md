# Skills

## User skills (`skills/`)

Install custom skills here (or under `~/.my-cowork/skills`). Each skill is a
folder with `SKILL.md` (Eigent format) or `skill.yaml`.

Imported zips land in this directory and appear under **您的技能**.

## 内置技能（`resources/example-skills/`）

随应用打包的技能（docx / pdf / pptx / xlsx / officecli* /
china-legal-counsel / official-document-writing / skill-creator /
skill-security-auditor）。
在界面 **内置技能** Tab 展示，只读不可删，
仍可通过 `~/.my-cowork/skills-config.json` 开关与权限范围配置。

`china-legal-counsel` 含本地法规知识库（约 35MB），已整包入库；
从上游刷新可用 `npm run vendor:china-legal-skill`。

`official-document-writing`（公文写作）为 Markdown 模板/清单技能；
Hub →「文档」→「公文写作助手」。Word 默认按正文稿规范
（`references/body-manuscript-format.md`：方正字体、行距 29 磅）。
从上游刷新可用 `npm run vendor:official-document-skill`（会套用
`scripts/patches/official-document-writing/` 本地排版）。
