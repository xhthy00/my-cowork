# Laravel 专项开发

> 本文件是 `dev-expert` 的 Laravel/PHP 框架专项补充参考，不作为独立子技能计数，也不提供 `@` 显式调用入口。命中 Laravel、Eloquent、Blade、artisan、Migration、Form Request、Queue、PHPUnit、PHPStan 等信号时，按需与 `code-generation`、`cms-development`、`mysql-database`、`api-design`、`software-project` 协同加载。

## 适用边界

- 适用：Laravel 应用开发、Eloquent 查询、Blade、API Resource、Form Request、Queue/Job、Migration、PHPUnit/Pest、PHPStan、部署缓存与性能配置。
- 不适用：PHP 内核开发、非 Laravel CMS 内核改造、未确认框架类型时的 Laravel 专用代码生成。
- PHP 版本：以项目 `composer.json`、CI 和线上环境为准。Laravel 新项目可优先 PHP 8.2+；使用 PHP 8.4 特性前必须确认运行环境支持。

## 架构规则

1. Controller 保持薄层：只做认证授权、请求校验、调用服务/Action、返回 Response。
2. 业务编排优先放 Service 或单用途 invokable Action；模型只承载关系、scope、accessor、mutator 和领域内聚行为。
3. HTTP 边界使用 Form Request；复杂输入通过 `toDto()` 转成类型明确的参数对象。
4. API 输出使用 Resource 或 Resource Collection，禁止 Controller 直接返回 raw model / `toArray()` 作为长期契约。
5. 副作用使用 Event/Listener 或 Job 承接，避免在 Controller 中直接发通知、写缓存、调第三方。
6. 新抽象必须有真实复用点；少于 3 个调用点时优先内联，避免过度分层。

## Laravel API 设计

- 契约优先：先定义 Form Request 输入契约和 API Resource 输出契约，再写 Controller。
- 错误响应统一 envelope，例如 `{ "success": false, "error": { "code": "...", "message": "..." } }`。
- 新增字段优先于修改/删除字段；删除字段必须先标记 deprecated 并给迁移窗口。
- 第三方 API 响应一律视为不可信数据，进入业务逻辑前用 DTO 或专门校验类约束结构。
- 多租户/父子资源使用 scoped route model binding，避免跨租户越权。

## Eloquent 与查询规则

- 开发环境启用 `Model::preventLazyLoading(!app()->isProduction())` 捕获 N+1。
- 只选择必要列：`select(['id', 'title', 'user_id'])`，关联加载也指定列。
- 计数用 `withCount()` / `withExists()`，禁止加载完整关系后再 count。
- 批量更新优先数据库级操作；但涉及 observer、audit、事件、文件清理时必须逐模型 `save()` 或显式说明绕过原因。
- 大数据处理使用 `chunkById()` / lazy collection，并明确并发写入风险。
- 批量插入/更新优先 `upsert()`，并说明唯一键和更新列。
- 模型禁止 `$guarded = []`，必须使用显式 `$fillable` 或受控 DTO。

## 常见生产坑

| 场景 | 风险 | 处理方式 |
| - | - | - |
| `Model::where()->update()` | 跳过 Eloquent observer、audit、model events | 需要事件时用 `lockForUpdate() + save()`；确实批量绕过时写明原因 |
| `attach/detach/sync/updateExistingPivot` | 直接写 pivot 表，不触发 pivot model events | 需要审计时把 pivot 建成真实模型并通过模型写入 |
| Observer 删除文件 | 父级路径清理可能误删兄弟记录文件 | 删除动作限定到当前记录路径，复杂清理交给 Action |
| `chunkById + json_decode + update` | JSON 字段并发写入被旧快照覆盖 | 浅层修改用 DB 原子表达式；复杂修改需锁或维护窗口 |
| `DB::afterCommit()` | 只避免回滚时执行，不负责提交后失败重试 | 外部副作用默认改成 queued job + retry + failed 处理 |
| JsonResource 直接返回 Carbon | 可能绕过 model cast 的日期格式 | API 日期格式在 Resource 内显式 format 并测试 |
| 嵌套数组只写 `items.*.field` | 标量元素可能通过局部规则导致运行时报错 | 同时加 `items.* => array` |

## Migration 与数据变更

- 已在共享环境执行过的 migration 禁止回改；新增 migration 处理后续变更。
- DDL 和数据回填分离；大表变更优先 expand-contract：新增列 -> 回填 -> 切读写 -> 删除旧列。
- 外键用 `foreignId()->constrained()`，频繁过滤列要加索引并说明查询路径。
- 需要真正逐行提交/释放锁的 PostgreSQL migration，应设置 `$withinTransaction = false`；MySQL DDL 多数会隐式提交，仍需写回滚方案。
- 数据回填必须可重入，避免 `migrate:fresh` 或重跑时重复插入/误覆盖。

## Queue 与异步任务

- Job 必须实现失败路径：`failed(Throwable $exception)`、重试次数、退避策略、幂等键。
- 顺序依赖用 `Bus::chain()`，批处理用 `Bus::batch()`。
- 对外部 API 调用加限流和超时；重复请求用唯一键或 `ShouldBeUnique`。
- 状态变更 + 外部副作用优先使用事务后派发 job，并补偿失败状态。
- **与 Init-Step-Poll 桥接**：需向前端暴露进度 / 允许取消的长任务（批量导入导出 / 生成静态页 / 采集同步），用 `Init → Step → Poll` 包装 Queue Job——Init 派发 Job 并建任务记录、Step（或 Job 内部批处理）更新进度、Poll 查任务状态；纯后端异步可直接用裸 Queue，无需 Init-Step-Poll 包装。

## 生产就绪

- 启动期校验关键配置：API key、DSN、queue、cache、storage，缺失时 fail fast。
- 提供 `/health` 和 `/ready`：前者检查进程可响应，后者检查 DB/Redis/关键依赖。
- 部署前执行 `config:cache`、`route:cache`、`view:cache`，并确认动态配置不依赖运行时 `.env` 变更。
- OPcache、preload、JIT 只在确认 PHP 版本、框架兼容和回滚方式后开启。

## 验证命令

按项目实际工具选择，至少保留一条可复现证据：

```bash
composer validate
composer test
./vendor/bin/phpunit
./vendor/bin/phpstan analyse --level=8
php artisan test
php artisan route:list
```

## 关联 reference

- `code-generation`：实现 Controller、Service、Action、Job、Resource。
- `api-design`：接口契约、错误 envelope、版本策略、长任务 Init-Step-Poll。
- `mysql-database`：索引、事务、慢查询、迁移回滚。
- `test-generation` + `laravel-testing`：Feature Test、Factory、Fake/Mock。
- `software-project`：发布、回滚、监控、告警、巡检。
