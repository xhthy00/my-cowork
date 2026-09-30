# API设计

## 输入要求

1. **业务需求**（必填）：需要设计的业务场景和功能
2. **数据模型**（必填）：核心实体和字段
3. **接口类型**（可选）：RESTful或GraphQL，默认RESTful
4. **已有接口**（可选）：如果已有部分接口需要兼容
5. **特殊要求**（可选）：如"需要支持批量操作"、"需要Webhook回调"

## 执行流程

### 第一步：Spec场景检查

设计前检查是否有明确的spec：

- **如有spec**：提取spec中的Requirement和Scenario作为接口设计依据，确保每个Requirement对应至少一个端点，每个Scenario映射为接口的成功/错误响应
- **如无spec**：提示用户先使用 `spec-driven-development` 对齐需求，或基于业务需求生成轻量级spec

```
✓ Spec场景检查: [检测到/未检测到] 需求规格
[如检测到，列出 Requirement → 端点 映射]
```

### 第二步：需求分析

- 识别API的使用场景和用户
- 确定API的功能边界
- 明确输入输出数据模型

### 第三步：设计原则应用

- 应用RESTful或GraphQL设计原则
- 设计URL结构和HTTP方法
- 定义请求/响应格式

### 第四步：详细设计

- 设计每个端点的详细规范
- 定义错误处理策略
- 设计认证和授权机制
- 如接口涉及长任务/批处理/导入导出/生成任务，必须采用 `Init → Step → Poll` AJAX 渐进式防卡死架构

### 第五步：API规范定义

```markdown
## API Spec: [API名称]

### ADDED Requirements

#### Requirement: [端点名称]

The system SHALL provide an endpoint to [功能描述].

##### Scenario: 成功请求

- GIVEN [前置条件]
- WHEN 发送 `[METHOD] [路径]` 请求
- THEN 返回 [状态码] 和 [响应体]

##### Scenario: 错误处理

- GIVEN [错误前置条件]
- WHEN 发送 `[METHOD] [路径]` 请求
- THEN 返回 [错误状态码] 和 [错误响应体]

### Design

- **URL结构**: [结构说明]
- **认证方式**: [认证机制]
- **版本策略**: [版本管理]

### File Changes

- `[API定义文件]` (new/modified)

```

#### 规范验证（必填）

API规范定义完成后，必须完成以下验证才能进入文档生成：

- [ ] **契约一致性**：每个 Requirement 至少有一个 Scenario 覆盖，Scenario 的 Given/When/Then 完整
- [ ] **错误码完备**：每个端点定义了成功和至少一类错误场景的错误码
- [ ] **认证/授权**：需要鉴权的端点标注了认证方式和所需权限
- [ ] **分页/限流**：列表端点定义了分页参数和限流策略
- [ ] **幂等性**：写操作标注了是否幂等，非幂等操作定义了重试策略
- [ ] **命名规范**：路径、字段、错误码遵循统一命名规范（如 snake_case / camelCase）
- [ ] **长任务契约**：耗时操作采用 Init-Step-Poll 模式，定义了任务ID、进度查询端点、取消端点和超时策略

如某项无法验证，必须在文档生成时标注"未验证项"，不得跳过。

### 第六步：文档生成

- 生成OpenAPI/Swagger规范
- 编写使用示例
- 提供SDK代码示例

### 第七步：记录到项目记忆

API 设计完成后，将关键决策和规范记录到项目记忆（参见 `project-memory-management.md`）：
- 记录 API 设计决策（如 RESTful vs GraphQL 选择理由）
- 记录接口命名约定和版本策略
- 记录认证/授权方案的选型依据

## 实战请求示例

### 示例一：分页查询接口

```text
帮我设计一个订单列表 API。
资源：orders。
查询条件：page、page_size、status、keyword、created_start、created_end。
权限：只有后台运营可访问；普通用户不能访问。
要求：分页最大 100；错误响应要有 code/message；keyword 支持订单号和手机号。
验证：给出正常请求、非法 page_size、无权限访问的响应示例。
```

优先加载：`api-design.md`、`mysql-database.md`、`test-generation.md`。

### 示例二：长任务导出接口

```text
帮我设计一个订单导出 API，数据量可能超过 10 万。
要求：不能单请求同步导出，必须 Init-Step-Poll；支持进度、失败原因、取消和重试。
权限：只有管理员可导出；导出文件 24 小时后过期。
前端：需要轮询字段和错误提示文案。
验证：给出 Init、Step、Poll、Cancel 的请求/响应示例。
```

优先加载：`api-design.md`、`frontend-design.md`、`test-generation.md`。

## 输出格式

````

## API设计文档

### 资源定义

| 资源 | 说明 | 核心字段 |
| -------- | ------ | ---------- |
| [资源名] | [说明] | [字段列表] |

### 接口列表

#### [接口名称]

**URL**：`[METHOD] /path`
**说明**：[功能说明]

**请求参数**：
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| [字段] | [类型] | [是/否] | [说明] |

**响应格式**：

```json
{
  "code": 0,
  "data": { ... },
  "message": "success"
}
```

**错误码**：
| 错误码 | 说明 |
|--------|------|
| [CODE] | [说明] |

### 通用规范

- **认证方式**：[Bearer Token / API Key / OAuth2]
- **版本控制**：[URL路径 / Header / 参数]
- **分页方式**：[页码分页 / 游标分页]
- **数据格式**：[snake_case / camelCase]

### 长任务接口规范（如适用）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/tasks/{type}/init` | POST | 创建任务，返回 `task_id`、`total`、初始状态 `queued` |
| `/tasks/{task_id}/step` | POST | 执行一批处理，返回进度和 `has_more` |
| `/tasks/{task_id}/poll` | GET | 查询任务状态、进度、错误和结果 |
| `/tasks/{task_id}/cancel` | POST | 标记任务取消，返回 `status=cancelled`；正在执行的 Step 在下一批次检测取消标记后优雅退出 |

**Step 响应必须包含**：`task_id`, `status`, `processed`, `total`, `percent`, `has_more`, `message`, `errors`

````

## 质量标准

- URL必须使用名词复数形式，不能用动词（如/users而非/getUsers）
- HTTP方法必须符合语义（GET无副作用、POST创建、PUT幂等更新、DELETE删除）
- 错误响应必须包含机器可读的错误码和人工可读的消息
- 分页接口必须说明最大页大小和默认页大小
- 敏感操作（删除、批量修改）必须要求二次确认或特殊权限
- 不得设计返回超大列表的接口（必须分页或流式）
- 长任务/批处理接口必须采用 `Init → Step → Poll`，不得设计为单请求同步阻塞执行
- Step 接口必须幂等、可重试，并限制单批处理数量

## 失败回退机制

| 步骤 | 失败条件 | 回退目标 | 最大重试 | 不可恢复时升级路径 |
| - | - | - | - | - |
| 第一步：Spec场景检查 | 无spec且业务需求模糊 | 基于业务需求生成轻量级spec草案 | 1 | 标注"需求未对齐"，建议先走 Spec驱动开发 |
| 第二步：需求分析 | 业务场景涉及多个领域，边界不清 | 拆分为多个子API分别设计 | 2 | 输出需求拆分建议，由用户确认后继续 |
| 第三步：设计原则应用 | RESTful与GraphQL均不完全契合 | 选择主风格+局部例外，标注例外原因 | 1 | 输出两套方案对比，由用户决策 |
| 第四步：详细设计 | 认证/授权机制与现有系统冲突 | 降级到最简认证（Bearer Token），标注待对齐 | 2 | 输出认证方案选型矩阵，移交架构决策 |
| 第五步：API规范定义 | 端点数量过多导致单次输出超限 | 按资源域分批输出，每批3-5个端点 | 0 | 建议拆分为多个API版本迭代设计 |
| 第六步：文档生成 | OpenAPI规范生成失败 | 降级为Markdown表格文档，标注"未生成机器可读spec" | 2 | 输出手写文档模板，建议人工补全 |
| 第七步：记录到项目记忆 | 项目记忆系统不可用 | 输出Decision Record到本地文件 | 1 | 标注"记忆未沉淀"，提示用户手动保存 |

## 关联 reference

- **tech-selection**（技术选型）— 设计前可用 `tech-selection` 确定API技术方案（REST/GraphQL/gRPC）
- **code-generation**（代码生成）— 设计后可用 `code-generation` 生成API接口代码
- **test-generation**（测试用例生成）— 设计后可用 `test-generation` 生成API测试
- **doc-generation**（文档生成）— 设计后可用 `doc-generation` 生成API文档
- **project-memory-management**（项目记忆管理）— 记录 API 设计决策、接口命名约定和版本策略
