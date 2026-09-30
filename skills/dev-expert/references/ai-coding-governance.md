---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: f114db32c8f49bbd4c4c544cd9de808d_678e1d60a09d11f1a65b525400826444
    ReservedCode1: Z9/MqsY/z2ETEHxaVajVfslhLwvwhN5d2R9OKmu8Q6mBmERJWqaPYLmmuc4s7jRqp10tWLZkcSH1u8U3yNGg8/5K/iXdSuQkfJlxr6CM03Smy9RyX5PU5bJebWs2m4xYQP7igaVBUWMNxx4cGH6AoHcO9UmwEnfEIW6mPxsrVB7aMY35bIbKCcxUVPY=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: f114db32c8f49bbd4c4c544cd9de808d_678e1d60a09d11f1a65b525400826444
    ReservedCode2: Z9/MqsY/z2ETEHxaVajVfslhLwvwhN5d2R9OKmu8Q6mBmERJWqaPYLmmuc4s7jRqp10tWLZkcSH1u8U3yNGg8/5K/iXdSuQkfJlxr6CM03Smy9RyX5PU5bJebWs2m4xYQP7igaVBUWMNxx4cGH6AoHcO9UmwEnfEIW6mPxsrVB7aMY35bIbKCcxUVPY=
---

# AI 编码治理（ai-coding-governance）

> 工程纪律层专项（v1.17.0 起）：为仓库/组织设定 AI 编码 Agent 的行为边界、数据边界、验证要求与可追溯性。不替代 `code-review`（单 diff 审查）与 `llm-application-security`（LLM 应用运行时安全）。

## 铁律

```
无边界、无验证、无归属的 AI 改动 = 不可接受的改动
```

编码 Agent 若无法说清「改了什么 / 为什么改 / 怎么验证的 / 触碰了哪些数据」，该改动不可接受。本专项的目标是让 AI 生成代码与人类改动达到同一验收标准。

## 适用场景

- 为 Trae / CodeBuddy / Cursor / Claude Code 等编码 Agent 编写仓库级规则（允许与禁止动作、保护路径、数据边界、必选验证）
- 项目引入 AI 辅助编码后，出现"Agent 深夜改 12 个文件、没跑测试、diff 无归属"等问题
- 需要约束 Agent 不越权触碰敏感数据、密钥、生产配置
- AI 生成改动涉及生产代码、基础设施、测试、文档、迁移或发布产物
- 需对 Agent 输出做可追溯、有界、安全的验收

## 不适用场景

- 单个 PR / diff / 分支的 pre-merge 审查 → `code-review`（本专项管"规则"，`code-review` 管"按规则审具体 diff"）
- 主风险是 prompt 注入 / 工具越权 / LLM 应用运行时安全 → `llm-application-security`
- 主问题是模型评测 / 检索增强评测 / Agent 任务评测 → 见 LLM 评估专项（未内置时按威胁建模协同）
- 通用审查路由、变更大小策略、流程指标（无 AI Agent 控制决策）→ 不加载

## 治理清单（8 项）

### 第一步：划定 Agent 行为边界

- 列出允许任务（实现 / 修 Bug / 重构 / 写测试 / 生成文档）与禁止任务（删库、改生产配置、动权限、发消息、扣费操作）
- 定义保护路径：哪些目录 / 文件禁止写入（如 `.ssh/`、`.env`、`vendor/`、`node_modules/`、生产配置、凭据文件）
- 定义选择规则：什么场景允许 Agent 自主决策，什么场景必须回问用户

### 第二步：编码仓库指令

- 将编码风格、测试要求、安全规范、数据处理、依赖引入、发布预期编码为 Agent 可读的规则文件（如 `AGENTS.md` / `CLAUDE.md` / 项目约定文件）
- 指令必须是"可检查的断言"而非"良好愿望"——每条规则对应一个可 grep / 可 lint / 可测试的验证项

### 第三步：保护数据

- 禁止 Agent 将密钥、敏感记录、私有日志、非必要用户数据带入上下文或写入产出
- 需要读取敏感数据时，先脱敏再进上下文；读后即弃，不写入任何持久化文件
- 触及数据边界时触发安全闸门：先说明风险与处理动作，不展开敏感值

### 第四步：要求小且可解释的 diff

- 每次改动保持小范围：机械编辑与行为变更分离，一次只改一个关注点
- 改动须附带意图说明；无法一句话解释的 diff 视为可疑，退回重做
- 多文件批量改动须走「批量修改 7 防线」（预检→试点→备份→执行→后检→MD5→回读）

### 第五步：强制验证记录

- Agent 改动落地前必须产出验证证据（测试输出 / lint 输出 / 静态检查结果 / 显式说明无法验证的原因）
- 未附验证证据的改动视为未完成（对齐 SKILL.md Step 4「无证据 = 未完成」）
- 关键改动（生产代码 / 迁移 / 发布产物）须有用户显式确认记录

### 第六步：依赖引入管控

- 新依赖必须说明：用途、更新路径、许可与安全理由、实验性依赖的移除计划
- 引入前过审查门禁（作者 / 维护度 / 许可 / 已知漏洞 / lockfile 锁定），见 `threat-modeling` 供应链部分

### 第七步：追踪 Agent 工作痕迹

- 记录：提示词、工具动作、改动文件清单、验证输出、用户确认
- 生产风险改动必须保留完整追溯链；追溯链缺失的改动不得交付

### 第八步：持续调优规则

- 将 Agent 反复犯的错误转化为更明确的指令、测试或自动化检查
- 高频坑记入 `error-ledger`（ERR-XXX），命中即复用正确判据

## 输出契约

治理方案落地须产出以下产物（至少一项，用户可见）：

- 仓库规则文件（如 `AGENTS.md` / 项目约定），含：允许/禁止动作、保护路径、数据边界、必选验证
- 生成代码验收检查表（Agent 改动过检清单）
- 敏感路径清单与触碰响应预案

## 验证

- 规则文件逐条可检查：每条规则对应一个验证命令或检查项
- 抽样 3 条规则做"攻击测试"：故意让 Agent 越界，确认规则能拦下
- 运行 hooks 安全扫描（`secret_scan` / `security_scan`）确认数据边界生效

## 协同路径

- 制定规则 → `code-review`（按规则审 diff）→ `error-ledger`（沉淀高频坑）
- 引入 Agent 依赖 → `threat-modeling`（供应链门禁）
- 涉及 LLM 应用本身 → `llm-application-security`
*（内容由AI生成，仅供参考）*
