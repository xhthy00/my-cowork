# Laravel 测试专项参考

> 本文件是 `test-generation` 的 Laravel/PHPUnit 补充参考，不作为独立子技能计数。命中 Laravel、PHPUnit、Pest、Feature Test、Factory、Queue fake、HTTP fake、Sanctum 等信号时按需加载。

## 测试分层

- Feature Test：覆盖 HTTP、路由、中间件、授权、校验、数据库副作用，是 Laravel 业务功能的默认优先级。
- Unit Test：覆盖纯服务、Action、值对象、规则类，不依赖 HTTP，尽量少碰数据库。
- Integration Test：覆盖队列、外部服务适配器、缓存、文件系统等跨边界行为。
- Regression Test：每个已修复缺陷至少补一条失败先行或可复现用例。

## 基础规则

1. 一个测试只验证一个主要行为，命名使用 `test_` 前缀或清晰的 `it ...` 描述。
2. 同时断言响应和副作用：HTTP status、JSON 结构、数据库状态、队列/事件/通知是否派发。
3. 所有测试数据优先使用 Factory，禁止在业务测试里散落 raw `DB::table()->insert()`。
4. Fake 必须在 action 前设置：先 `Queue::fake()`，再执行请求，最后断言。
5. 外部 HTTP、邮件、通知、队列、事件、Storage 默认 fake，除非当前测试明确验证真实集成。
6. 涉及权限时同时测允许路径和拒绝路径。

## 数据库策略

- `RefreshDatabase`：默认选择，保证 migration 与测试数据库一致。
- `DatabaseTransactions`：更快，但不能验证 migration；仅在项目明确适配时使用。
- `DatabaseMigrations`：每个测试运行/回滚 migration，成本高，只在需要验证迁移行为时使用。
- 数据库断言使用 `assertDatabaseHas()`、`assertDatabaseMissing()`；金额 DECIMAL 按字符串断言，避免 float 精度问题。

## Feature Test 模板

```php
public function test_user_can_update_own_profile(): void
{
    Queue::fake();

    $user = User::factory()->create();

    $response = $this
        ->actingAs($user)
        ->patchJson('/api/profile', [
            'name' => 'Ada Lovelace',
        ]);

    $response
        ->assertOk()
        ->assertJsonPath('success', true)
        ->assertJsonPath('data.name', 'Ada Lovelace');

    $this->assertDatabaseHas('users', [
        'id' => $user->id,
        'name' => 'Ada Lovelace',
    ]);

    Queue::assertNothingPushed();
}
```

## 校验与授权测试

- 表单校验：断言 422、字段错误、不会产生数据库副作用。
- 授权拒绝：断言 403 或项目统一错误 envelope。
- 认证缺失：断言 401，并确认不会泄露内部错误。
- API Resource：断言字段存在、敏感字段不存在、关系字段只在 `whenLoaded()` 时出现。

## Factory 模式

- 每个核心模型都应有 Factory。
- 状态使用 `state()`：如 `active()`、`suspended()`、`verified()`。
- 关系通过 Factory 组合创建，不在测试主体里手写大量依赖数据。
- 需要副作用的测试可使用 `afterCreating()`，但要避免隐藏过多业务前置条件。
- 批量场景使用 sequence 覆盖不同状态和边界值。

## Fake 与 Mock

| 工具 | 用途 | 断言 |
| - | - | - |
| `Queue::fake()` | 队列任务 | `assertPushed()`、`assertNothingPushed()` |
| `Event::fake()` | 领域事件 | `assertDispatched()` |
| `Notification::fake()` | 通知 | `assertSentTo()` |
| `Mail::fake()` | 邮件 | `assertSent()`、`assertQueued()` |
| `Storage::fake()` | 上传/文件写入 | `assertExists()`、`assertMissing()` |
| `Http::fake()` | 外部 API | `assertSent()`、模拟超时/错误 |
| `Bus::fake()` | chain/batch | `assertChained()`、`assertBatched()` |

服务类 mock 只用于隔离外部边界或昂贵依赖；核心业务规则优先真实执行，避免测试只验证 mock 调用。

## N+1 与性能回归

- 对列表接口记录查询数量基线，新增关系字段时必须复测。
- 使用 `with()`、`withCount()`、`withExists()` 后断言响应字段和查询数量。
- 性能断言不替代功能断言；如需量化性能，协同 `performance-benchmark`。

## 长任务与队列测试

- Init-Step-Poll 接口需覆盖：初始化成功、重复初始化幂等、单步成功、单步失败、轮询完成、轮询失败。
- Job 需覆盖：成功路径、异常重试、幂等重复执行、`failed()` 补偿。
- 批处理需覆盖：`then`、`catch`、`finally` 的状态变更。

## 运行命令

```bash
php artisan test
./vendor/bin/phpunit
./vendor/bin/phpunit --filter test_user_can_update_own_profile
./vendor/bin/phpstan analyse --level=8
```

## 交付证据

交付 Laravel 测试相关任务时，至少提供：

- 新增/修改的测试文件路径。
- 运行命令。
- 通过/失败结果。
- 如失败，给出阻塞原因和下一步所需输入。
