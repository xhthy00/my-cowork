---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: f114db32c8f49bbd4c4c544cd9de808d_68ffff87a09d11f1a238525400e6dd8f
    ReservedCode1: TwrMaRICscAXxg6RIZ5N2wtNRaqzmUsO2obK+b1v2ae5809WVRmgS2sS1KNdfrlV/Mm9jo2+t61BGTYQ5Z0ItArZ/8ZaiIjdGk0opleqdA5tJer52aPK9P7cUI+G8muis0ggC8m66tgC5yr4hmHurVaTj1tXJOc77bziIgW6BUW3Xk57HtDW90LikDM=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: f114db32c8f49bbd4c4c544cd9de808d_68ffff87a09d11f1a238525400e6dd8f
    ReservedCode2: TwrMaRICscAXxg6RIZ5N2wtNRaqzmUsO2obK+b1v2ae5809WVRmgS2sS1KNdfrlV/Mm9jo2+t61BGTYQ5Z0ItArZ/8ZaiIjdGk0opleqdA5tJer52aPK9P7cUI+G8muis0ggC8m66tgC5yr4hmHurVaTj1tXJOc77bziIgW6BUW3Xk57HtDW90LikDM=
---

# 面向 Agent 的代码可读性（code-readability-for-agents）

> 工程纪律层专项（v1.17.0 起）：以"AI Agent 能否一次定位"为标准的仓库可读性审查。仓库的读者现在至少一半是 Agent——Agent 找不到规范实现，是结构问题，不是 Agent 的问题。

## 铁律

```
Agent 一次工具调用定位不到规范实现 → 结构就是错的
```

人类靠记忆忍受的间接层，会变成 Agent 的静默失败：改错文件、重复造已存在的函数、幻觉出"差一点就对上"的辅助函数。

## 适用场景

- 为 AI 辅助贡献准备代码库：降低改错文件、幻觉 helper 的概率
- Agent 反复"改错文件 / 重建已有函数 / 产出与本地约定差一点就对的 diff"
- 代码库有 god 文件、超出合理阅读预算的文件、名字无法预示内容的模块
- 代码搜索对常见动词（`process` / `handle` / `update` / `run`）返回多个疑似匹配，Agent 猜错
- 规划重构时，希望模块边界让未来的 Agent 和人类都能推理
- 入职（人或 Agent）成本高于工作本身——规范实现被间接层埋没

## 不适用场景

- 跨服务 / 跨系统边界的宏观架构决策 → `architecture-decision`
- 依赖清理、死代码删除、静态分析存量问题 → 代码卫生类协同（见 `threat-modeling` 之外的依赖纪律）
- 组织级 AI 编码规则（验收检查、数据边界、保护路径）→ `ai-coding-governance`
- 单个 Agent diff 的 merge 前审查 → `code-review`
- 文档生命周期、负责人、新鲜度 → 文档纪律（`doc-generation` 协同）
- 暴露面的 API 契约设计或向后兼容 → `api-design`

## 工作流

### 第一步：圈定范围

- 明确仓库范围：哪些目录在审查内，哪些是 vendored / 生成代码 / 有意遗留，直接排除
- 收集 Agent 近期轨迹：改错文件的实例、找不到规范实现而重建的实例、幻觉 helper 的实例

### 第二步：绘制模块边界图

- 列出顶层包 / 目录、声明的职责、实际导出的内容
- 标注"规范实现唯一归属"：某项行为应当且只应当在一个位置实现
- 交叉引用检查：同一行为出现多个实现 → 标记合并候选

### 第三步：命名冲突审计

- 列出跨模块重复的函数 / 类名，公共动词用作名字的情况，大小写 / 近形碰撞
- 对领域高频动词和名词，实测代码搜索返回多少个候选匹配、外人如何从中挑选
- 命中 ≥ 3 个候选的公共名称 → 重命名或加模块前缀，保证唯一命中

### 第四步：文件与函数体量预算

- 输出最大文件、最长函数、最深嵌套清单，对照已约定的体量预算（无预算先定一个）
- 超出预算的文件给出拆分建议：按职责拆分，而非按行数机械切分
- 函数超过单屏可读范围 → 拆 init / calc / final 等子函数

### 第五步：可定位性验证

- 对领域常见查询（"订单状态在哪改""这个格式化函数在哪"），模拟 Agent 单次工具调用能否定位
- 定位失败的条目 → 输出命名 / 布局补丁：重命名、挪位置、加模块 README / doc string
- 验证标准：一次调用到达规范实现，且没有第二个"看起来也对"的候选

### 第六步：测试与文档协同定位

- 检查测试放置约定（代码旁 / 平行树 / 分散）：Agent 找测试的能力预测其验证能力
- 不满足"一个函数 → 一眼找到对应测试"的 → 列为改进项
- 每个模块应有简短 README / doc string：声明职责、公共表面、非显然不变量

## 输出契约

审查须产出（至少一项，用户可见）：

- 仓库可读性地图：模块边界图 + 命名冲突清单 + 体量报告 + 定位失败清单
- 命名 / 布局补丁建议（按"一次调用可定位"标准排序）
- 明确结论：哪些结构在 Agent 视角下"不可读"——不许以"人类能看懂"为由放行

## 验证

- 对每条定位失败项：改完后用模拟单次调用复测，确认唯一命中
- 对命名冲突项：代码搜索返回候选数从 ≥3 降至 1
- 体量项：超出预算文件数量归零或显式接受例外并登记
- 抽查 Agent 实跑：给 Agent 一个"改某处行为"的任务，观察是否一次改对

## 协同路径

- 结构改造 → `refactoring`（落地拆分 / 重命名，先建验证路径）
- 规范实现归属 → `architecture-decision`（边界级决策）
- 后续 Agent 表现仍差 → `ai-coding-governance`（规则补漏）
*（内容由AI生成，仅供参考）*
