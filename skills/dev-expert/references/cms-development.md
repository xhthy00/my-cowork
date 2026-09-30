# CMS二次开发

面向基于 PHP+MySQL 的 CMS 二次开发场景，提供从环境探测、兼容性修复、插件开发到安全加固的全链路指引。覆盖 EmpireCMS、WordPress、ThinkPHP、Laravel 等主流 CMS/框架。

## 输入要求

1. **开发任务**（必填）：需要实现的二次开发功能或修复目标
2. **CMS 类型与版本**（可选）：如未提供，按自动探测流程识别
3. **PHP 版本**（可选）：如未提供，按默认策略选择
4. **已有代码**（可选）：涉及修改的现有代码片段或文件路径

## 执行流程

### 第一步：CMS 自动探测

逐项匹配，命中即停：

| 特征文件 | CMS |
| - | - |
| `e/class/connect.php` | EmpireCMS |
| `wp-config.php` | WordPress |
| `thinkphp/base.php` 或 `vendor/topthink` | ThinkPHP |
| `artisan` + `bootstrap/app.php` | Laravel |
| `system/core/CodeIgniter.php` | CodeIgniter |
| `data/config.php` + `simplewind/` | ThinkCMF |
| `index.php` + `data/conf/` | DedeCMS |
| `composer.json` 含 `slim/slim` | Slim |
| `composer.json` 含 `hyperf` | Hyperf |
| `composer.json` 含 `yii` | Yii |

**未确认 CMS 类型前，禁止生成任何框架特定代码。**

```
✓ CMS探测: [CMS名称] [版本号]
  特征文件: [匹配到的特征文件]
  表前缀: [数据库表前缀]
  配置文件: [配置文件路径]
```

### 第二步：环境与版本确认

#### PHP 版本选择

| CMS | 最低版本 | 推荐版本 | 注意事项 |
| - | - | - | - |
| EmpireCMS 7.5 | 7.4 | 8.2 | 需 PHP 8 兼容补丁 |
| WordPress 6.x | 7.4 | 8.2 | 部分老插件可能不兼容 8.3+ |
| ThinkPHP 6 | 7.4 | 8.2 | |
| ThinkPHP 8 | 8.0 | 8.2 | |
| Laravel 9 | 8.0 | 8.1 | |
| Laravel 10 | 8.1 | 8.2 | |
| Laravel 11 | 8.2 | 8.3 | |
| CodeIgniter 4 | 7.4 | 8.2 | |
| DedeCMS v5.7 | 5.6 | 7.4 | 不支持 PHP 8 |
| Hyperf | 8.0 | 8.2 | 建议跟随 Swoole 版本 |

**版本选择原则**：优先匹配 CMS 要求 → 用户指定版本 → 默认 8.2

#### PHP 可执行文件探测协议

**严禁硬编码 PHP 路径**（如 `F:\BtSoft\php\` 仅是当前用户本地环境，跨用户/跨平台不可用）。LLM 在执行 lint/运行脚本前，必须按以下优先级链探测 `PHP_BIN`：

| 优先级 | 探测源 | 适用场景 | 示例 |
| - | - | - | - |
| 1 | 环境变量 `PHP_BIN` | 用户显式指定 | `set PHP_BIN=F:\BtSoft\php\85\php.exe` |
| 2 | 环境变量 `PHP_{VERSION}`（如 `PHP_82`） | 多版本共存时按版本指定 | `set PHP_82=F:\BtSoft\php\82\php.exe` |
| 3 | 系统 PATH 中的 `php` 命令 | 已加入 PATH 的环境 | `php -v` 可用 |
| 4 | 常见安装位置自动扫描 | 宝塔/XAMPP/Homebrew 等默认安装 | 见下表 |
| 5 | 询问用户并写入 `PHP_BIN` | 以上均未命中时，强制询问 | 用户确认后写入环境变量 |

**常见安装位置默认值**（优先级 4，按平台扫描）：

| 平台 | 扫描路径 | 探测特征 |
| - | - | - |
| Windows | `F:\BtSoft\php\{ver}\php.exe` / `D:\phpstudy\php\{ver}\php.exe` / `C:\xampp\php\php.exe` / `C:\Program Files\php\php.exe` | 目录存在且 `php.exe` 可执行 |
| macOS | `/opt/homebrew/bin/php@{ver}` / `/usr/local/bin/php@{ver}` / `/Applications/MAMP/bin/php/php{ver}/bin/php` | 文件存在且可执行 |
| Linux | `/usr/bin/php{ver}` / `/usr/local/bin/php{ver}` / `/opt/php/{ver}/bin/php` | 文件存在且可执行 |

**多版本共存处理**：

- 当用户规则中声明多版本（如 7.4/8.0/8.1/8.2/8.3/8.4/8.5）时，按「版本选择原则」确定目标版本号
- 用目标版本号匹配 `PHP_{VERSION}` 环境变量（如目标 8.2 → 查 `PHP_82`）
- 未匹配到精确版本时，回退到 `PHP_BIN` 或 PATH 中的 `php`
- 探测过程必须输出日志：`[PHP-PROBE] 目标版本 8.2 → 优先级 X → 命中: {实际路径}`

### 第三步：数据库操作规范

#### 存储引擎

默认 **InnoDB**（支持事务、行锁、崩溃恢复，与 `mysql-database.md` 对齐）；只有该 CMS 历史项目已大规模使用 MyISAM 且无事务需求时，才显式标注保留 MyISAM。

#### 访问层优先级

1. CMS 官方数据访问层（WP: `$wpdb` / TP: `Db` 类 / Laravel: Eloquent / ECMS: `$empire->query()`）
2. PDO 预处理（兜底）
3. **禁止** `mysql_*` / `mysqli_*` 原生函数（CMS 内核已封装除外）

#### 查询安全红线

| 场景 | 禁止 | 强制 |
| - | - | - |
| 条件拼接 | `"WHERE id=$id"` | Prepared Statements |
| LIKE | `LIKE "%$kw%"` | `LIKE CONCAT('%', ?, '%')` |
| IN 子句 | 手动拼串 `IN(1,2,3)` | 动态占位符 `IN(?,?,?)` |
| 批量写入 | 循环单条 INSERT | 事务 + VALUES 批量 |
| 结果集 | 无限制全量拉取 | LIMIT/OFFSET 或游标 |

#### 类型映射

| MySQL 类型 | PHP 类型 | 说明 |
| - | - | - |
| INT/BIGINT | `int` | |
| DECIMAL | `string` | 禁止 float，防金额精度丢失 |
| DATETIME | `DateTimeImmutable` | 或 CMS 原生时间类 |
| JSON | `array` | MySQL 5.7+ 原生类型 |
| NULL | `null` | 禁止用空字符串替代 |

#### 会话设置

```sql
SET NAMES utf8mb4;
SET time_zone = '+08:00';
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

#### CMS 数据库差异

| CMS | 表前缀 | 配置文件 | 特殊字段 |
| - | - | - | - |
| EmpireCMS | `phome_` 可自定义 | `e/config/config.php` | 信息表分主表+副表+索引表 |
| WordPress | `wp_` 可自定义 | `wp-config.php` | `wp_options` 存序列化数据 |
| ThinkPHP | 无默认前缀 | `config/database.php` | 遵循 ORM 定义 |
| Laravel | 无默认前缀 | `.env` | Migration 管理结构 |
| DedeCMS | `dede_` | `data/common.inc.php` | 旧式 `mediumint` 主键 |

### 第四步：PHP 8.x 兼容性检查

对现有代码执行兼容性扫描：

| 规则 | 严重度 | 修复 |
| - | - | - |
| 数组键加引号 | 致命 | `$arr[key]` → `$arr['key']` |
| 可选参数不可先于必选参数 | 弃用 | 交换参数顺序 |
| `each()` | 已移除 | 改用 `foreach()` |
| `create_function()` | 已移除 | 匿名函数 |
| `$HTTP_RAW_POST_DATA` | 已移除 | `php://input` |
| `(real)` 类型转换 | 已移除 | `(float)` |
| `get_magic_quotes_gpc()` | 已移除 | `function_exists()` 包裹 |
| `strftime()` | 已弃用 | `date()` 或 `DateTime::format()` |
| 双引号内 `${var}` | 已弃用 | `{$var}` |
| `#` 注释中的 `#[` | 属性冲突 | 改用 `//` 注释 |

**兼容性验证命令**（路径由 PHP 探测协议动态获取，以下用 `{PHP_BIN}` 和 `{PHP_BIN_LOW}` 占位）：

```bash
# 目标版本 lint
{PHP_BIN} -l file.php
# 低版本兼容检查（用 PHP_74 环境变量或探测到的 7.4 路径）
{PHP_BIN_LOW} -l file.php
```

### 第五步：安全红线检查

| 漏洞 | 最低防护 |
| - | - |
| SQL 注入 | 内部接口也必须参数绑定 |
| XSS | 输出必须 `htmlspecialchars(..., ENT_QUOTES, 'UTF-8')` 或 CMS 等效函数 |
| CSRF | 状态变更操作必须验证 Token |
| 文件上传 | MIME 校验 + 扩展名白名单 + 重命名 + 非执行目录 |
| 反序列化 | 禁止对不可信数据使用 `unserialize()`，改用 JSON |
| 密码 | `password_hash()` / `password_verify()`，禁止 MD5/SHA1 |
| Include | 禁止 `include $user_input`，路径必须白名单或固定 |

### 第六步：插件/模块开发

#### 开发标准

- **一功能一文件**：独立功能一个 PHP 文件，清晰分明
- **命名**：`action_module_function.php`
- **目录**：按功能模块分子目录
- **入口**：单一入口，不暴露内部文件
- **依赖**：通过 CMS 标准 API 调用，不跨插件直接 include

#### IDE 通用排除目录

CMS 缓存（`data/dbcache/`、`data/fc/`、`runtime/`、`e/tmp/`）、第三方依赖（`vendor/`、`node_modules/`）、上传附件（`uploads/`、`d/file/`）、备份导出（`backup/`、`sql_dump/`、`back/`）、版本控制（`.git/`、`.svn/`）应加入 IDE 排除列表，避免索引和监视。

#### AJAX 渐进式防卡死架构

CMS 后台长任务必须优先采用 `Init → Step → Poll` 架构，禁止单请求同步执行到底。

**强制适用场景**：

- 批量导入/导出、批量更新、批量删除
- 生成静态页、重建索引、清理缓存、图片压缩
- 内容采集、远程同步、第三方接口批量拉取
- 预计执行时间超过 3 秒，或处理数据量超过 100 条

**端点职责**：

| 端点 | 职责 | 必须返回 |
| - | - | - |
| Init | 校验权限/CSRF/参数，创建任务记录，计算总量 | `task_id`, `total`, `status=queued` |
| Step | 每次只处理一小批数据，更新进度和错误列表 | `processed`, `total`, `percent`, `has_more` |
| Poll | 前端轮询任务状态，不执行重业务逻辑 | `status`, `percent`, `message`, `errors` |
| Cancel | 标记任务取消，不立即杀进程 | `status=cancelled`，正在执行的 Step 在下一批次检测取消标记后退出 |

**实现约束**：

- 每个 Step 必须限制批量大小，例如 20-100 条，避免 PHP 超时
- 任务状态必须持久化到数据库、缓存或任务文件，不能只依赖 PHP 内存
- Step 必须可重复调用，使用游标/offset/last_id 保证幂等
- 状态变更必须校验登录态、权限和 CSRF Token
- 错误必须记录到任务错误列表，允许部分失败后继续处理
- 前端必须显示进度、当前批次、失败数、重试/取消入口
- Step 每批次开始必须检测取消标记，若已取消则停止处理并标记 `status=cancelled`，不允许继续执行剩余批次
- 僵尸检测：Poll 发现 `status=running` 且 `updated_at` 超过阈值（建议 2× 单批预估耗时或固定如 30 分钟）无更新，标记为 `failed`（僵尸）或允许客户端 `resume` 重跑未完成批次；前端据此展示"任务疑似中断，可重试"
- Poll 间隔建议 800-2000ms，连续失败 3 次后停止并提示

**最小响应示例**：

```json
{
  "task_id": "build_20260702_001",
  "status": "running",
  "processed": 120,
  "total": 500,
  "percent": 24,
  "has_more": true,
  "message": "正在处理第 120/500 条",
  "errors": []
}
```

### 第七步：代码风格与质量

**核心原则**：二开/插件生成的代码风格必须与原项目**已有实际代码**一致，而不是 Agent 想象或技能示例风格。

**强制步骤（生成/修改前）**：按 `style-alignment.md`「风格嗅探协议」先取样目标项目 1-2 个代表性已有文件（同目录/同模块优先），提取缩进、开标签、括号位置、数组键引号、模板变量命名（如 `$navinfor`/`$empire`）、PHP/HTML 混编方式等标记，产出「风格基线」块，逐行对齐后再写。

**风格套用优先级**（与风格基线冲突时以基线为准；仅当项目无任何可参照文件时回退到下表）：
CMS 官方规范 > `.editorconfig`/`phpcs.xml` > **风格基线（项目现有风格）** > 下表内置约定（兜底） > PSR-12

| 类型 | 约定（兜底默认值） | 示例 |
| - | - | - |
| 类名 | PascalCase | `UserController` |
| 方法/函数 | camelCase | `getUserById()` |
| 变量 | camelCase | `$userId` |
| 常量 | UPPER_SNAKE | `MAX_ATTEMPTS` |
| 字段/表名 | snake_case | `created_at` |
| 注释 | 中文 | `// 校验登录态` |

#### 五条自审

| # | 规则 | 判定标准 |
| - | - | - |
| 1 | 单一职责 | 每个函数只做一件事，不超过 40 行 |
| 2 | 早返回 | 异常先 return/throw，主逻辑不被 if 嵌套包裹超过 2 层 |
| 3 | 无魔法数字 | 硬编码数字/字符串提取为常量或配置 |
| 4 | 外部输入必校验 | `$_GET/$_POST` 在使用前校验类型和范围 |
| 5 | 错误处理闭环 | 每个 try 有 catch，每个 catch 有日志或提示，不吞异常 |

#### 技术债禁令

| # | 模式 | 正确做法 |
| - | - | - |
| 1 | `if($a = func())` 赋值当判断 | 拆两行：`$a = func(); if($a !== null)` |
| 2 | 函数返两种类型 `array\ | false` | 统一返回类型，空用 `[]`，异常用 throw |
| 3 | `global $var` 在函数内 | 改为参数传入或依赖注入 |
| 4 | `switch(true)` | 用 `match` 或 `if-elseif` 显式表达 |
| 5 | 注释掉的代码块留着 | 直接删除，Git 历史可恢复 |
| 6 | `else` 后紧跟 `if` 不合并 | 用 `elseif` 或提前 return 消除 else |
| 7 | 函数参数超过 5 个 | 封装为对象/数组或拆分子函数 |
| 8 | 循环内 `.=` 拼接大字符串 | 压入数组最后 `implode()` |

### 第八步：交付检查清单

| # | 检查项 | 方法 |
| - | - | - |
| 1 | 数组键加引号 | `grep -Pn '\$[a-z_]+\s*\[[a-z_]' *.php` |
| 2 | 无裸 SQL 拼接 | 人工审查 $_GET/$\_POST 直拼 |
| 3 | 输出已转义 | echo/print 后有无 htmlspecialchars |
| 4 | PHP Lint | `php -l file.php` |
| 5 | 错误日志已清空 | `> {PHP_ERROR_LOG}`（路径由 PHP 探测协议推断，通常为 `{PHP_DIR}/logs/php_errors.log` 或 `sys_temp_dir('php')/errors.log`） |
| 6 | 事务边界正确 | 写操作路径 try/catch + rollback |
| 7 | 长任务防卡死 | 批量任务采用 Init → Step → Poll，Step 有批量大小和进度持久化 |
| 8 | 依赖锁定 | 检查 `composer.lock` 是否存在并提交；`composer.json` 中无 `latest`/`*`/`dev-main` 浮动版本 |

**验证证据类型声明**（对齐主流程 Step 4，CMS 场景必填）：

| 证据类型 | 适用场景 | 最小字段 |
| - | - | - |
| 命令+输出 | PHP lint、PHP8 兼容扫描、grep 检查（数组键引号/裸 SQL/输出转义） | 命令文本 + 退出码 + 关键输出片段 |
| API 响应 | Init/Step/Poll 长任务接口联调（批量同步/导入导出/生成静态页） | Status Code + Response Body + 请求参数 |
| 测试报告 | 插件功能测试、批量任务回归、事务回滚验证 | 测试用例数、通过数、失败用例清单 |
| 截图+步骤 | 后台管理页面、CMS 模板渲染、H5 页面 | 截图 + 操作步骤 + 浏览器/PHP 版本 |

未声明证据类型的验证视为未完成（见 SKILL.md Step 4）。

### 第九步：记录到项目记忆

开发完成后，将关键决策记录到项目记忆（参见 `project-memory-management.md`）：

- 记录 CMS 类型、版本和 PHP 版本选择理由（Decision Record 模式）
- 记录数据库表结构和前缀约定（Convention Capture 模式）
- 记录安全加固措施和已知兼容性问题
- 记录插件/模块的目录结构和命名约定

## 实战请求示例

### 示例一：后台管理功能

```text
帮我给 WordPress 后台加一个订单备注管理页。
环境：WordPress 6.x，PHP 8.2，MySQL 8.0。
功能：按订单号搜索备注；新增/编辑备注；记录操作人和时间。
安全：使用 $wpdb prepare；后台权限校验；状态变更加 nonce；输出转义。
验证：给出数据库表结构、后台菜单入口、手动测试步骤和 PHP lint 命令。
```

优先加载：`cms-development.md`、`mysql-database.md`、`code-generation.md`。

### 示例二：帝国CMS 批量处理

```text
帮我给帝国CMS 7.5 做一个批量同步文章状态的后台工具。
环境：PHP 8.2，表前缀 phome_。
要求：先探测 CMS 和 PHP 版本；不能单请求跑完；必须 Init-Step-Poll；每批 100 条。
安全：后台登录态、权限、CSRF、输出转义；禁止直接改缓存文件。
验证：给出 Init/Step/Poll 响应示例、错误日志检查路径和清缓存说明。
```

优先加载：`cms-development.md`、`api-design.md`、`test-generation.md`。

## 输出格式

```markdown
## CMS 二次开发交付说明

### 1. 环境信息

- **CMS**: [名称] [版本]
- **PHP**: [版本]
- **数据库**: [类型] [版本]
- **表前缀**: [前缀]
- **配置文件**: [路径]

### 2. 变更文件清单

| 文件 | 操作 | 说明 |
| ------ | -------------- | ---------- |
| [路径] | 新增/修改/删除 | [功能说明] |

### 3. 数据库变更

| 类型 | SQL | 说明 |
| ------- | --------- | ---------- |
| DDL/DDL | [SQL语句] | [变更说明] |

### 4. 安全检查

| 检查项 | 状态 | 说明 |
| ------------ | ----------- | ------ |
| SQL 注入防护 | 通过/未通过 | [说明] |
| XSS 防护 | 通过/未通过 | [说明] |
| CSRF 防护 | 通过/未通过 | [说明] |
| 文件上传安全 | 通过/未通过 | [说明] |

### 5. 兼容性检查

| 检查项 | PHP [版本] | 说明 |
| -------- | ----------- | ------ |
| 语法兼容 | 通过/未通过 | [说明] |

### 6. PHP Lint 结果

| 文件 | 状态 |
| -------- | --------- |
| [文件名] | 通过/失败 |

### 7. 已知限制与后续建议

- [限制1]
- [建议1]
```

## 质量标准

- 未确认 CMS 类型前禁止生成框架特定代码
- 建表必须使用 InnoDB 引擎，MyISAM 仅在有明确 CMS 历史约束时保留
- 必须使用 CMS 官方数据访问层，禁止原生 SQL 拼接
- DECIMAL 金额字段禁止用 PHP float
- 输出必须转义（XSS 防护）
- 状态变更操作必须验证 CSRF Token
- PHP 8.x 兼容性必须通过 lint 检查
- 插件必须遵循一功能一文件、单一入口原则
- 代码风格必须遵循 CMS 官方规范 > PSR-12
- 禁止使用 `==`，统一 `===`

## 失败回退机制

| 步骤 | 失败条件 | 回退目标 | 最大重试 | 不可恢复时升级路径 |
| - | - | - | - | - |
| 第一步：CMS 自动探测 | 无特征文件匹配 | 列出最接近的 CMS 类型，要求用户确认 | 1 | 输出 CMS 特征检查清单，由用户手动确认 |
| 第二步：环境与版本确认 | 目标 PHP 版本与 CMS 不兼容 | 降级到 CMS 推荐的最低稳定版本 | 1 | 输出版本兼容矩阵，由用户决策 |
| 第三步：数据库操作规范 | CMS 数据访问层文档缺失 | 降级到 PDO 预处理，标注"未使用 CMS 原生 API" | 1 | 输出数据库操作建议，建议查阅 CMS 官方文档 |
| 第四步：PHP 8.x 兼容性检查 | 兼容性问题数量超出单次修复能力 | 按致命/弃用分级，优先修复致命项 | 2 | 输出兼容性问题清单，建议分批修复 |
| 第五步：安全红线检查 | 发现安全漏洞 | 立即修复，标注修复影响范围 | 0 | 安全问题零容忍，不发布含已知漏洞的代码 |
| 第六步：插件/模块开发 | CMS 插件机制文档不可用 | 按通用单一入口模式开发，标注"未遵循 CMS 插件规范" | 1 | 建议查阅 CMS 官方插件开发文档后补充 |
| 第七步：代码风格与质量 | 代码风格与 CMS 内核不一致 | 优先匹配 CMS 内核风格，标注风格差异 | 1 | 输出风格差异清单，建议统一 |
| 第八步：交付检查清单 | Lint 检查未通过 | 修复语法错误后重新检查 | 3 | 输出未通过文件清单，建议人工修复 |
| 第九步：记录到项目记忆 | 项目记忆系统不可用 | 输出 CMS 开发配置到本地文件 | 1 | 标注"开发配置未沉淀"，提示用户手动保存 |

## 关联 reference

- **frontend-design**（前端设计）— CMS 模板页面、后台管理页面、H5 页面需参考 `frontend-design.md` 的视觉、交互、响应式和浏览器验证规范
- **code-generation**（代码生成）— CMS 代码生成时参考本 Skill 的数据访问层和安全规范
- **bug-diagnosis**（Bug诊断）— CMS Bug 诊断时参考本 Skill 的 PHP 8.x 兼容性检查和常见模式
- **code-review**（代码审查）— CMS 代码审查时参考本 Skill 的安全红线和技术债禁令
- **tech-selection**（技术选型）— CMS 版本选型时参考本 Skill 的 PHP 版本推荐矩阵
- **mysql-database**（MySQL数据库）— CMS 表结构、索引、SQL、事务、慢查询和迁移回滚参考 `mysql-database.md`
- **project-memory-management**（项目记忆管理）— 开发配置和约定沉淀时参考本 Skill 的记录模板
