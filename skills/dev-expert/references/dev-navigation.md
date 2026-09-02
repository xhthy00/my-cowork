# 阶段导航（Dev Navigation）

> **定位**：**指路，不替用户跑**。用户问"下一步该做什么 / 现在进行到哪了 / 帮我串起完整流程 / 失败后该回哪一步"时，本专项只输出阶段检测与下一步建议，**不调用其他子技能、不写代码、不产出 artifact**。
> **触发**："下一步该做什么"、"what's next"、"现在在哪一步"、"帮我串起来"、"从需求到交付"、"完整跑一遍"、`--status` / `--next` / `--recover`。
> **与任务拆解的关系**：`task-decomposition-and-execution` 负责把任务拆成 Wave 并执行；本专项负责**流程级导航**——检测当前所处阶段并推荐下一动作，二者互补：拆解在前，导航贯穿全程。

## 第一步：检测当前阶段（现扫现答，不维护状态文件）

每次调用都从仓库现状**现扫现答**，不深读 artifact 内容、不维护 state file：

| 检测信号 | 判定阶段 |
| -------- | -------- |
| 无任何 design / spec / plan / fix 产物 | 需求阶段（Phase 0） |
| 有 spec / design 文件但无 plan | 设计阶段 |
| 有 plan / 任务清单但无代码改动 | 计划阶段 |
| 有代码改动 + 未提交测试 | 实现 / 测试阶段 |
| 有 failing test 或修复产物 | 修复阶段 |
| 测试全绿 / 实现完成 | 验证阶段（审查前） |
| 有合并 / PR / 发布记录 | 已完成闭环，可复盘 |

扫描路径（按项目实际存在取其一）：
- `.design-context.md` / `specs/` / `docs/specs/` / `{PROJECT_ROOT}/.ai-memory/handoff.md`
- `.claude/artifacts/{designs,plans,fixes}/`（若项目使用）
- `.ai-memory/` 下 topics / session_memory / daily（见 `project-memory-management`）

## 第二步：输出当前状态与下一步

**默认模式**（用户给原始需求 / 不确定该做什么）：

1. **分类**：路径 = feature / bug / hotfix；复杂度 = 简单 / 复杂
2. **扫现状**：按第一步检测当前阶段
3. **推荐链**：给出从当前阶段到收尾的完整链路 + 每条链路的下一步

**`--next` 模式**：只输出一条命令 / 一个动作 + 一句 rationale，不展开。

**`--status` 模式**：只输出当前 phase 检测结果，不推荐。

**slug 处理**：多个 in-flight 任务时列出让用户指定；仅 1 个时默认使用；0 个（新需求）时先提案 slug 让用户确认。

## 第三步：失败恢复（`--recover`）

用户报告某一步失败（BLOCK / REJECT / NEEDS_DESIGN_CHANGE / 验证失败）时，按失败类型推荐回到哪一步：

| 失败信号 | 回到 | 为什么 |
| -------- | ---- | ------ |
| 需求没对齐 / 业务规则不明 | 需求澄清（SKILL.md Step 1.5） | 规格不明，后续全错 |
| spec 与实现不一致 | 设计阶段重对齐 spec | 实现基于错误规格 |
| 测试失败（非 Bug） | 实现阶段修实现 | 区分"实现错"与"规格错" |
| 测试失败（确为 Bug） | 修复阶段（`root-cause-debugging`） | 先复现失败再修根因 |
| 审查发现问题 | 实现阶段修复问题项 | 按审查清单闭环 |
| 收尾 / 交付失败 | 验证阶段 | 处理阻塞项 / 补收尾清单 |

**不替用户拍板**：路径（feature / bug / hotfix）和复杂度模糊时，列选项让用户选。

## 第四步：推荐链参考（完整流程）

- **feature 路径**：需求澄清 → Spec 对齐（`spec-driven-development`）→ 计划（`task-decomposition-and-execution`）→ TDD / 实现（`code-generation` + `test-generation`）→ 验证（Step 4）→ 审查（`code-review`）→ 交付收尾（`delivery-assurance`）
- **bug 路径**：Triage → 复现失败测试 → 根因追溯 → 修复 → 回归留仓（`root-cause-debugging`）→ 交付收尾
- **hotfix 路径**：Triage → 最小修复 → 验证 → 收尾 → 复盘（`incident-review`，若为线上事故）

## 输出模板

```
## 阶段导航

**当前阶段**：[阶段名 + 检测依据（哪个文件/信号）]
**进行中任务**：[slug / 描述]
**下一步**：[一个动作 + 一句 rationale]
**推荐链**：[从当前到收尾的链路，标注每个环节对应 reference]
**阻塞项**：[如有，含原因与建议动作]
```

## 失败回退

| 失败类型 | 动作 |
| -------- | ---- |
| 扫描信号不足（无任何 artifact） | 视为 Phase 0，按新需求走默认模式 |
| 多个 in-flight 无法判定 | 列出选项交用户指定，不猜 |
| 用户需求与检测阶段冲突 | 以用户明示意图为准，说明检测结果仅供参考 |

本专项**绝不写代码、绝不产出 artifact**——用户索要文档 / 实现时，回到对应子技能路由。
