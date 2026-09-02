# 项目知识图谱（代码结构认知层）

## 输入要求

1. **工作区根目录 `{PROJECT_ROOT}`**（必填）：项目代码根，图谱按工作区独立存储于 `{PROJECT_ROOT}/.ai-memory/knowledge-graph/`，与会话生命周期无关、可随时重建。
2. **改动文件清单**（P1 规划前置可选）：跨模块改动时传入"本次拟改文件集"，用于查"改动闭包"而非全量。
3. **查询入口**（P3 显式查询可选）：`file`（相对路径）或 `symbol`（类名/函数名，经 symbols.json 解析）。

## 定位与边界

- **受众**：图谱唯一受众是 agent 开发时借全局视角理解项目；**不生成 mermaid**（人类可视化源，agent 不加载，纯冗余）。人类兜底为 `graph.md`（文本邻接表，agent 不读）。
- **与"任务依赖图"区分**：本图谱是**代码结构依赖（持久、跨会话）**；`task-decomposition` / `software-project` / `refactoring` 里的"依赖图"是**任务执行依赖（临时、本次任务内）**。前者称"代码结构图谱"，后者称"任务依赖"，命名严格拉开。
- **与现有机制互补**：① 延迟加载协议——查图谱替代全仓扫；② `project-memory`——结构层 vs 决策层，互引不重叠；③ 不进记忆蒸馏、不参与 Git 团队共享。
- **纯 agent 加速器，非验证替代品**：正常改动靠它快定位；动刀前 grep 复核那一下不能省（见硬门禁）。

## 执行流程

### 第一步：触发规模门控

| 场景 | 行为 |
| - | - |
| 简单任务 / 单文件（L0） | **不触发**，图谱是噪声 |
| 跨模块改动 / 重构 / 审计 / 接手陌生项目（≥3 文件） | 主动查图谱（先走新鲜度校验） |
| 显式 `@project-knowledge-graph` 或"画依赖图/模块关系" | 构建 / 查看 / 查询 |
| 文件变更后下次查询 | 哈希比对自动判定过期 → 提示或增量重建 |

### 第二步：构建 / 冷启动（工具侧抽取，token ≈ 0）

调用 `scripts/build_graph.py`（纯脚本写盘，不进 LLM 上下文）：

```bash
# 全量构建
python scripts/build_graph.py --root {PROJECT_ROOT} --rebuild

# 查时若图不存在 → 冷启动：先全量构建再查（见第三步）

# 内置 E2E 自检（删文件无悬挂边 + 改文件过期判定，不改交付物）
python scripts/build_graph.py --root {PROJECT_ROOT} --selftest
```

- **抽取技术**：v1 默认纯正则静态抽取（零依赖、跨平台、秒级、多语言通用，无 AST/tree-sitter）；LSP 仅做可用性探测（`detect_lsp` 记 `lsp_available`），抽取仍走正则（语义增强为可选留口，当前未实现）。结果写 `meta.json.lsp_available`。
- **语言范围**：PHP / JS（一等支持）；Java / Python / TS / Go 同样建图（通用正则粗边），LSP 可用仅记录、不改变抽取方式。
- **原子写**：graph.json / meta.json / symbols.json 均先写 `.tmp` 再 `rename` 覆盖，避免半文件。
- **抽取自校验（准确性硬保障，构建阶段强制）**：
  1. **边目标反查剔除悬空边**：每条 include/require/import 边解析为绝对路径后校验目标是否存在；不存在 → 判悬空边，**不写入有效边集**，仅记入 `meta.json.dangling_edges`（含源:行号 + 解析值 + 所用 base）。base 解析规则：源文件目录优先；无 `./`/`../` 前缀且非绝对 → 回退 include_path + 工作区根；两路都解析不到才判悬空。
  2. **符号孤儿仅告警不裁决**：类/函数节点反查 `symbols.json` 找不到定义 → 标 `orphan` 提示，**不自动删节点/边**（symbols 自身可能漏抽导致误标）；真正剔除须查后动作 grep 复核确认。
  3. **覆盖率自检报告**：写 `meta.json.accuracy_report`（`edges_total` / `edges_valid` / `edges_dangling` / `symbols_*` / `static_coverage` / `lsp_available`）；构建日志输出 `[GRAPH-ACCURACY] 有效边 X / 悬空 Y（已剔除）/ 覆盖率 Z% / LSP: php`。

### 第三步：查询接口与子图裁剪（核心，决定 agent 怎么用图谱）

```bash
python scripts/build_graph.py --root {PROJECT_ROOT} --query <file|symbol> [--direction up|down|both] [--depth N]
```

- `--query`：`file` 直接定位；`symbol` 经 `symbols.json` 解析为文件:行号再查（无索引则打印"符号索引缺失"并返回空子图，不扫描全图）；多个入口用逗号分隔（如 `--query a.php,b.php`），返回合并子图；同名符号歧义 → 返回候选列表（每个含文件:行号 + 所属 module），由模型/用户选定其一。
- `--direction`：上游依赖（谁依赖它）/ 下游（它依赖谁）/ 双向。
- `--depth N`：**默认 2 跳**——防止一次查询把半个项目读进上下文，守住"省 token"承诺。
- **环检测**：遍历维护已访问集合，遇已访问节点折叠标记 `cycle:true` 不再展开，杜绝 A→B→A 膨胀/死循环；输出附 `[GRAPH-CYCLE] 检测到 N 个环`。
- **节点预算硬上限**：子图节点数超 `MAX_NODES=80` 即截断（防枢纽模块 2 跳爆炸，如 `connect.php`）。
- **输出**：仅返回 N 跳内 `{nodes, edges, cycle}` 紧凑 JSON 片段（预计 2K–10K token）进入上下文。

### 第四步：新鲜度校验（最关键，防失效误导）

**唯一判定机制：查时比对哈希**（不依赖 PostToolUse 脏标记，避免双套逻辑分裂）：

- 每次**查图谱前**比对 `meta.json` 文件清单 vs 当前工作区：先用 **mtime 粗筛**（mtime 未变 → 直接判未过期），仅变更文件重算**内容哈希精筛**。
- 过期 → 输出 `[GRAPH-STALE] 图谱可能过期（N 个文件变更），正在增量重建…` 并触发重建（v1 增量=全量重抽，统一覆盖增/删/改/重命名四类）；或直接提示用户重建。
- **冷启动**：`meta.json`/产物缺失（首次使用或图被误删）→ 输出 `[GRAPH-STALE] 图谱可能过期（N 个文件变更/产物缺失），正在增量重建…` 并当场全量构建；构建完成再查。若自主度低或构建耗时过长 → 降级为"临时 grep 局部依赖"并在交付标注"图谱未构建，已用临时分析替代"，不阻断主任务。

### 第五步：查后动作规范（C，决定"改动更稳"落地）

模型拿到子图后必须显式转化为执行动作，而非"看了眼"：

1. 若入口为"待改模块"，列出子图内**所有上游依赖方（谁依赖它）** → 纳入改动影响评估范围。
2. 对受影响文件清单，**在修改阶段一并改、在验证阶段一并跑 lint/断言**（防漏改依赖方）。
3. 输出"影响面摘要"给用户（改 A 会影响 B/C，已纳入范围），作为交付"已知限制/范围"的一部分。

### 第六步：硬门禁（双保险底线，图谱不准时也不轻信交付）

自校验保证"不准的边不进图"（第二步），但漏抽（动态依赖）自校验发现不了，须靠门禁兜底——以下任一条不满足，**不得交付，且 SELF-AUDIT 直接判不通过**：

- **G1 grep 冲突以 grep 为准**：图谱影响面结论与 grep 实测不符 → 一律以 grep 为准，图谱仅作提示，不得用图谱覆盖 grep 结果。
- **G2' 图谱影响面须附 grep 实测证据**：图谱给出的影响面清单，**必须**经独立 grep 复核（对清单内每个文件确认真实依赖）；交付物须**附 grep 原始输出片段**（如 `grep -rn "class X" 命中 N 处 @ file:line`），SELF-AUDIT 核对证据存在且覆盖清单全部文件；**无证据即判不通过，卡在交付前**（与"无验证证据=未完成"红线同源）。agent 不能靠自评绕过谎报。
- **G3 不可逆操作单独确认**：删 / 重命名 / DDL 等不可逆操作，**不单凭图谱结论**执行；必须独立 grep 复核真实依赖 + 走用户确认闸门（复用既有"破坏性操作默认取消"铁律）。

## 作用点锚定（实施时写入 SKILL.md Step 2 / Step 3，不靠 agent 猜测）

| 作用点 | 触发条件 | 钉到 Step | 查什么 | 产出落哪 |
| - | - | - | - | - |
| **P1 规划前置依赖分析** | 复杂任务（≥3 文件 / 跨模块）进方案阶段 | **Step 2 规划（PLAN-GATE 前）** | **改动文件集闭包**（`--query <改动文件1,改动文件2,…> --direction both --depth 3`），非项目全量 | 喂 `_plan.md` 依赖矩阵，替代临时 grep |
| **P2 执行前局部影响面** | Step 3 要改具体模块 | **Step 3 执行（改码前，先新鲜度校验）** | 该模块 2 跳上游（`--query <模块> --direction up --depth 2`） | 喂查后动作规范（受影响文件一并改+验证） |
| **P3 显式请求** | 用户 `@project-knowledge-graph` 或"画依赖图/模块关系" | 任意 Step，用户直接要 | 按用户入口 | 构建/查看/查询 |
| **不触发** | 简单任务 / 单文件（L0） | — | — | 图谱是噪声，跳过 |

- **P1 vs P2 不冲突**：P1 全量广度（喂 plan），P2 局部深度（喂执行），互补。
- **默认链路**：`复杂任务 → Step 2 前 P1 查全量依赖 → 写 plan 依赖矩阵 → Step 3 改某模块前 P2 查上游 → 查后动作规范 → 执行`。

## 存储 Schema

```
{PROJECT_ROOT}/.ai-memory/knowledge-graph/
├── graph.json      # 节点 + 边（结构化，机器读，agent 唯一消费源）
├── meta.json       # 构建时间、工具版本、文件清单哈希、范围配置、覆盖率、accuracy_report、script_hash
├── graph.md        # 文本邻接表（人类可读兜底，agent 不加载）
└── symbols.json    # 符号索引：类名/函数名 → 文件:行号（支撑 --query <symbol>）
```

- **节点**：file（默认粒度）/ module（目录级聚合单元，按源码根下一级业务目录推导，v1 不做 namespace 细聚）。
- **边类型**：`include`（含 require/require_once/include_once，统一归 include）`use`（命名空间 use）`autoload`（new \Ns\Class / \Ns\Class:: 自动加载）`extends`（类继承）`template`（{include file=}/template()）`tpimport`（ThinkPHP import()/vendor()/Loader::import()）`import`（非 PHP 语言模块导入）`cssimport`（CSS @import）`asset`（HTML link/script 资源）`calls`（跨文件调用）。注：`implements`/`require` 非独立边类型——`require` 并入 `include`，`implements` 作为类属性记录、不单独成边。
- **敏感边约束**：`calls` 边只记跨文件/跨模块调用，过滤标准库/框架内置/密钥读取等内部调用，避免泄露敏感路径且降噪。
- **不参与记忆蒸馏**：图谱基于代码、随代码重建，不纳入"超 30 天蒸馏/删除"。
- **多工作区切换**：会话切换 `{PROJECT_ROOT}` 时图谱上下文随之切换，互不干扰。

## 输出格式

- **agent 消费三件套**：`graph.json`（节点+边，唯一结构化输入）+ `meta.json`（构建/覆盖率/新鲜度）+ `symbols.json`（符号索引）。一律走 `--query` 查询接口返回裁剪子图 JSON，绝不读全量文件。
- **人类兜底**：`graph.md`（文本邻接表），仅供人类开发者偶尔查看；**agent 不加载**。
- **明确排除**：不生成 `graph.mmd` / mermaid；不在 README/FAQ 展示渲染图。

## 质量标准

1. 构建阶段 LLM token ≈ 0（输出写盘不进上下文）。
2. `--query` 返回 N 跳子图 token < 10K（深度默认 2 + MAX_NODES=80 上限兜底）。
3. 自校验生效：悬空边不进有效边集、孤儿仅告警不裁决、构建日志输出 `[GRAPH-ACCURACY]`。
4. 增量四类覆盖：删文件后图谱无悬挂边；改文件后查图谱触发过期判定（STALE）。
5. 降级可用：构建失败不阻断主任务，回退临时 grep + 交付标注"图谱不可用"。

## 失败回退机制

| 失败类型 | 回退动作 |
| - | - |
| 构建脚本缺失 Python / 权限 / 环境异常 | 降级为"临时 grep 局部依赖"，交付标注"图谱不可用，已用临时分析替代"，不阻断主任务 |
| 图谱过期但重建超时 | 同降级：临时 grep + 标注 |
| 符号索引缺失（--query <symbol> 无结果） | 返回空子图 + 提示"符号索引缺失"；仍无果 → 临时 grep |
| 图谱影响面与 grep 冲突（G1） | 一律以 grep 为准，图谱仅作提示 |
| 动刀前未 grep 复核（G2'） | SELF-AUDIT 判不通过，卡交付前，补 grep 证据 |
| 不可逆操作仅凭图谱（G3） | 独立 grep 复核 + 用户确认闸门 |
| 子图超 80 节点（枢纽模块） | 查询自动截断 + 提示缩小入口/降 depth |

## 常见陷阱

- **动态拼路径漏抽**：`require($base.'/class/'.$c.'.php')` / `import(resolve(dirname))` 正则抽不出，属通用边界（非某框架特有），README 须明示"不宣称 100% 结构还原"；漏抽兜底在查后动作 grep 复核 + 用户反馈纠偏闭环。
- **图谱≠真相**：漏抽自校验无真相可比对，不会报错也不会补全，故门禁 G1/G2'/G3 是最后底线。
- **绝对路径 target 未归一化**：构建时若源用 `ECMS_PATH` 等常量拼绝对路径，edges 会出现绝对路径 target（如 `j:/devx-sim/e`），查询时按相对路径匹配会失配——后续可考虑在 build 内归一化（可选优化，不影响现有相对路径边）。
