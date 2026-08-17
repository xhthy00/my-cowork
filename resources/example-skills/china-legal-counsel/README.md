# China Legal Counsel Skill

中国大陆企业资深法务顾问 Codex Skill。它面向合同审查、合同起草、法律风险分析、AI/数据/广告/IP/劳动/公司治理合规检查，以及本地法律知识库检索与更新。

> 本项目用于辅助法律研究和法务工作流，不替代执业律师或人工法务复核。重大交易、诉讼、监管、刑事、证券、并购、数据出境等高风险事项应交由专业人士处理。

---

## 关于作者

这个开源工具来自我们的企业 AI 服务实践——

我们核心提供**企业 AI 服务**，具体业务包括：

1. **企业 AI 培训**
2. **企业 AI 转型咨询**
3. **落地工具搭建、AI 工具定制及 Skill 定制**
4. **企业 AI 转型全程陪跑**

感兴趣可扫码添加微信 👇

![扫码添加微信](./assets/poster.png)

---

## 这个 Skill 能做什么

- **合同审查**：识别高风险条款、缺失条款、格式条款、违约责任、付款验收、知识产权、保密、数据处理、争议解决等问题。
- **合同起草**：生成 NDA、服务协议、采购/销售协议、授权协议、顾问协议、平台条款等草案，并给出谈判口径。
- **法律咨询**：围绕中国大陆法律进行事实拆解、风险分级、法律依据检索、行动建议和升级判断。
- **合规检查**：覆盖 AI 生成内容、算法推荐、深度合成、个人信息、数据安全、广告营销、知识产权、消费者保护、平台经营等场景。
- **引用校验**：要求结论基于用户材料、官方法规、司法解释、案例或本地知识库，不凭空编造法律条文。
- **知识库维护**：内置脚本可继续抓取、清洗、切分、搜索和校验官方法律资料。

## 知识库规模

当前随 Skill 内置的 `knowledge-base/` 约 **18MB**，整个 Skill 约 **35MB**。

- 已注册信息源：42 个
- 已抓取官方原始材料：24 份
- 已清洗 Markdown 文档：24 份
- 按条切分法规片段：2189 个

首批覆盖材料包括民法典、公司法、民法典合同编通则司法解释、个人信息保护法、数据安全法、广告法、著作权法、商标法、专利法、生成式 AI 暂行办法、AI 内容标识办法、网络数据安全管理条例、互联网广告管理办法、算法推荐规定、深度合成规定、个人信息出境标准合同办法、网络反不正当竞争规定等。

## 目录结构

```text
china-legal-counsel/
├── SKILL.md                         # Codex Skill 入口与工作流
├── agents/openai.yaml               # Codex UI 展示元数据
├── references/                      # 合同审查、起草、合规、引用校验等工作手册
├── scripts/                         # 知识库抓取、清洗、切分、搜索、引用校验脚本
└── knowledge-base/
    ├── 00_registry/                 # 信息源、核心法规、抓取策略
    ├── 01_raw/                      # 官方原始 HTML/PDF 和元数据
    ├── 02_clean/                    # 清洗后的 Markdown/JSON
    ├── 03_chunks/                   # 按条切分后的检索片段
    └── 07_evals/                    # 评测用例和幻觉陷阱
```

## 安装方式

把仓库放到 Codex skills 目录：

```bash
git clone https://github.com/Daknniel-0881/qulv-china-legal-counsel-skill.git ~/.codex/skills/china-legal-counsel
```

然后在 Codex 中直接提出法律/合同/合规类任务，或显式调用：

```text
Use $china-legal-counsel to review this contract under China mainland law.
```

## 常用命令

在 Skill 根目录运行：

```bash
python3 scripts/ingest_source_registry.py
python3 scripts/kb_search.py "格式条款 说明义务" --limit 5
python3 scripts/fetch_official_sources.py --ids gen_ai_interim_measures_2023
python3 scripts/normalize_legal_doc.py knowledge-base/01_raw/official_laws/example.html
python3 scripts/chunk_legal_doc.py knowledge-base/02_clean/markdown/example.md --kind law
python3 scripts/verify_citations.py legal_output.md
```

## 来源原则

本 Skill 优先使用：

1. 用户提供的合同、事实、业务背景和内部模板。
2. 国家法律法规数据库、中国人大网、中国政府网、最高人民法院、人民法院案例库等官方来源。
3. 国家网信办、市场监管总局、国家知识产权局、药监局等监管来源。
4. 官方合同示范文本、国家标准、地方司法/仲裁来源。
5. 已授权商业数据库和律所文章，仅作补充参考。

## 安全边界

以下事项必须升级给执业律师或人工法务复核：刑事风险、监管调查/处罚回复、证券披露、反垄断、数据出境、重大敏感个人信息处理、并购融资、群体性劳动争议、事故处理、公开声明、诉讼策略、证据保全/销毁风险，以及任何规避法律、伪造证据、逃税或违法伤害他人的请求。

## License

MIT
