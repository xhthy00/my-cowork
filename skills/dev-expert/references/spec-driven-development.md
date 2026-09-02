# Spec驱动开发 -- 需求规格对齐

## 输入要求

1. **需求描述**（必填）：需要实现的功能或变更
2. **项目上下文**（可选）：现有系统状态、相关模块
3. **已有spec**（可选）：如果已有spec需要增量修改
4. **约束条件**（可选）：性能、安全、兼容性要求

## 执行流程

### 第一步：明确意图（Proposal）

用3句话以内说明：

- **Intent**：为什么要做这个变更
- **Scope**：变更范围（In scope / Out of scope）
- **Approach**：大致技术方向

**示例**：

```
Intent: 用户请求添加暗黑模式以减少夜间使用时的眼疲劳
Scope: In scope - 主题切换、系统偏好检测、localStorage持久化
        Out of scope - 自定义颜色主题、按页面覆盖主题
Approach: CSS自定义属性 + React Context管理状态
```

### 第二步：模糊需求深挖与边界案例

遇到"合理、快速、稳定、安全、兼容、优化、友好、简单、智能、自动、尽快、可扩展"等模糊表述时，必须先转化为可验收标准，再编写 Requirements。

| 深挖维度 | 需要回答的问题 | 输出要求 |
| - | - | - |
| 判断标准 | 什么情况下算满足？用什么指标判断？ | 给出可测试阈值、规则或示例 |
| 适用边界 | 哪些场景覆盖，哪些不覆盖？ | 写入 In scope / Out of scope |
| 正向案例 | 哪些输入/场景应当通过？ | 至少 1 个 Given/When/Then |
| 反向案例 | 哪些输入/场景应当拒绝、报错或降级？ | 至少 1 个边界或失败 Scenario |
| 常见误区 | 容易被误解成什么？ | 明确不做什么，避免范围扩散 |
| 验证证据 | 如何证明已经满足？ | 测试、截图、API响应、benchmark、用户验收 |

**示例**：

```markdown
模糊词："快速"
判断标准：列表接口 P95 响应时间 SHALL 小于 300ms，测试数据量为 10,000 条。
正向案例：GIVEN 10,000 条数据 WHEN 请求第一页 THEN P95 < 300ms。
反向案例：GIVEN 缺少索引 WHEN 查询复杂筛选 THEN 系统 SHALL 返回明确超时提示或降级结果。
常见误区：不承诺所有历史数据导出都在 300ms 内完成；导出走异步任务。
```

### 第三步：编写 Requirements（ADDED/MODIFIED/REMOVED）

按变更类型生成三类 Requirements，使用 RFC 2119 关键词（MUST/SHALL/SHOULD/MAY），每个 Requirement 至少一个 Scenario。

#### ADDED Requirements（新增功能）

```markdown
## ADDED Requirements

### Requirement: [需求名称]

The system SHALL [具体行为描述].

#### Scenario: [场景名称]

- GIVEN [前置条件]
- WHEN [用户操作/系统事件]
- THEN [预期结果]
- AND [额外预期结果]
```

#### MODIFIED Requirements（修改现有功能）

```markdown
## MODIFIED Requirements

### Requirement: [需求名称]

The system MUST [新行为描述].
(Previously: [原行为描述])

#### Scenario: [场景名称]

- GIVEN [前置条件]
- WHEN [用户操作/系统事件]
- THEN [新预期结果]
```

#### REMOVED Requirements（移除功能）

```markdown
## REMOVED Requirements

### Requirement: [需求名称]

[移除原因说明]
```

### 第四步：编写Design（技术方案）

```markdown
## Design: [变更名称]

### Technical Approach

[技术实现思路，1-2段]

### Architecture Decisions

- Decision: [决策点]
  - Reason: [选择理由]
  - **Alternatives Considered**: [被否决的候选方案]
  - **Rejected Because**: [反选理由 / 该候选的 trade-off 为何不可接受]
  - **Trade-offs Accepted**: [本方案接受的代价与已知技术债]
  - **Revisit When**: [什么条件下重新评估此决策]

> ⚠️ 重点：存在**多候选方案 / 高影响决策**时，必须显式写出「反选理由」与「接受的代价」，仅给最终方案视为不完整——这是把架构权衡推理外显、防止盲执行的核心要求。单一合理实现的低复杂度改动可跳过反选论证，避免"澄清过度"反模式。

### File Changes

- `[文件路径]` (new/modified/deleted)
```

### 第五步：生成Tasks（实现清单）

```markdown
## Tasks

### Wave 1（无依赖，可并行）

- [ ] Task 1.1: [具体任务]
- [ ] Task 1.2: [具体任务]

### Wave 2（依赖Wave 1）

- [ ] Task 2.1: [具体任务]
```

### 第六步：编码前Spec验证

在开始编码前，检查：

- [ ] 每个Requirement是否有至少一个Scenario
- [ ] 每个Scenario是否可测试（有明确的Given/When/Then）
- [ ] 成功标准是否明确（"系统应该..."而非"系统可能..."）
- [ ] 变更范围是否聚焦（没有无意识扩散）
- [ ] 模糊词是否已转化为判断标准、边界案例和验证证据

**如无spec，提示**：

```
⚠️ 未检测到spec。建议先完成spec对齐再编码。
用 `spec-driven-development` 生成spec，或提供已有spec。
```

**如有spec，作为编码依据**：

```
✓ 检测到spec。编码时将严格按以下scenario实现：
- [Scenario列表]
```

### 第七步：记录到项目记忆

Spec验证通过后，将需求规格和设计决策记录到项目记忆（参见 `project-memory-management.md`）：
- 记录 Spec 的 Intent/Scope/Approach（Decision Record 模式）：作为后续编码和审查的依据
- 记录 Design 中的架构决策和 File Changes 清单（Convention Capture 模式）
- 若 Spec 编写中暴露需求歧义或新发现约束，更新到项目规范防止后续重蹈

## 输出格式

```
## Spec: [变更名称]

### Proposal
Intent: [意图]
Scope: [范围]
Approach: [方向]

ADDED Requirements:
...

MODIFIED Requirements:
...

REMOVED Requirements:
...

### Design
...

### Tasks
...

### Spec验证
- [ ] Requirements可测试
- [ ] Scenarios覆盖主路径和边界
- [ ] 成功标准明确
```

## 质量标准

- Spec是**行为契约**，不是实现计划（不写具体类名/函数名）
- 使用RFC 2119关键词：MUST/SHALL（绝对要求）、SHOULD（建议）、MAY（可选）
- 每个Requirement至少一个Scenario
- Scenario使用Given/When/Then格式，可转化为自动化测试
- 保持轻量：大多数变更使用Lite spec（简短需求+验收检查），高风险变更才用Full spec
- 模糊需求必须先深挖为判断标准、正反边界案例和验收证据，不得直接进入编码

## 失败回退机制

| 步骤 | 失败条件 | 回退目标 | 最大重试 | 不可恢复时升级路径 |
| - | - | - | - | - |
| 第一步：明确意图（Proposal） | 用户需求过于模糊，无法提炼Intent/Scope/Approach | 列出2-3种理解，要求用户选择 | 2 | 输出"需求澄清问卷"，等待用户补充后继续 |
| 第二步：模糊需求深挖与边界案例 | 模糊词无法转化为验收标准 | 列出 2-3 个互斥解释，请用户选择 | 2 | 输出"需求澄清问卷"，等待用户补充后继续 |
| 第三步：编写 Requirements（ADDED/MODIFIED/REMOVED） | Requirement过于宽泛，无法生成可测试Scenario | 拆分为多个子Requirement，每个对应一个Scenario | 2 | 输出Requirement骨架，标注"待细化"，由用户补充 |
| 第四步：编写Design（技术方案） | 技术方案与现有架构冲突 | 输出冲突点 + 备选方案 | 1 | 移交架构决策，输出Architecture Decision Record |
| 第五步：生成Tasks（实现清单） | 任务依赖关系复杂，无法清晰分组为Wave | 按文件维度分组，标注"粗粒度依赖" | 1 | 输出依赖图，建议拆分为多个独立spec |
| 第六步：编码前Spec验证 | Scenario不可测试或Given/When/Then不完整 | 退回第三步修订Scenario | 2 | 输出"spec不完整"清单，建议人工补充后再编码 |
| 第七步：记录到项目记忆 | 项目记忆系统不可用 | 输出Spec和Design到本地文件 | 1 | 标注"规格未沉淀"，提示用户手动保存 |

## 关联 reference

- **task-decomposition-and-execution**（任务拆解与执行）— spec完成后用 `task-decomposition-and-execution` 将tasks转为可执行计划
- **code-generation**（代码生成）— 编码时用spec作为验收依据
- **code-review**（代码审查）— 审查时检查实现是否符合spec
- **project-memory-management**（项目记忆管理）— 将spec和design决策记录到项目记忆
