# 任务管理行业应用样例

此样例通过现有 FastAPI 后端进程提供任务 API，通过工作台内的独立页面显示任务。任务保存在行业应用自己的 SQLite 数据目录中。

## 打包与安装

在项目根目录执行：

    python3 scripts/pack-industry-app.py examples/taskboard -o /tmp/taskboard-1.0.0.zip

打开 MyCowork 的“工作台”，点击“安装 ZIP”，选择该文件。阅读 Python 代码信任提示并确认。确认后平台自动启用；卡片显示“可用”后即可打开页面。

开发 Python 接口时保持 backend/mcapp_cn_example_taskboard 为唯一顶层包名。页面资源放在 frontend/dist，index.html 使用相对路径加载 JS/CSS。页面只能通过工作台的 postMessage 桥接请求 /api/apps/cn.example.taskboard 下的业务 API。

本样例提供只读“查询任务”和需宿主确认的“创建子任务”。选中任务后可分析风险、生成 Markdown 周报或拆分子任务；业务分区始终为 `local`，Python 工具校验宿主传入的选中范围。AI 详情按需覆盖业务页面，展开后进入同一工作区会话；返回恢复路由和选择，草稿由示例保存在 sessionStorage。

示例声明 A2 的 `ai`、`files`、`navigation`、`ui` 宿主能力，需使用包含这次升级的宿主，不兼容尚未实现 A2 的团队旧版本。文件首段支持 2 MB 以内的 UTF-8 文本材料和 Markdown 报告；Python 第三方依赖及任意宿主调用仍未开放。A3 随包提供风险分析与周报技能：两个按钮各选择对应技能，拆分子任务不选择技能。正文及文本资料随插件统一安装、升级和停用；这些技能是平台示例，尚不是经过业务验收的行业标准。完整桥接契约见[开发指南](../../docs/开发/行业应用插件开发指南.md#从业务页面使用宿主-ai-a2)。

包清单仍使用 schema v1。执行 `backend/.venv/Scripts/python.exe examples/taskboard/make-upgrade.py <输出 ZIP>` 可生成 v2 数据迁移样例，使用“从 ZIP 更新”验证已有记录与失败恢复。

A4 静态样例共用页面 SDK：修改 packages/app-sdk 后运行 node examples/taskboard/build-sdk.cjs，再执行打包命令。开发预览可运行 npm run app -- dev examples/taskboard；前端资源变化刷新，后端/技能变化输入 r。完整流程与独立目录规则见开发指南的本地开发工具章节。
