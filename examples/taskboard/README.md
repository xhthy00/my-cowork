# 任务管理行业应用样例

此样例通过现有 FastAPI 后端进程提供任务 API，通过工作台内的独立页面显示任务。任务保存在行业应用自己的 SQLite 数据目录中。

## 打包与安装

在项目根目录执行：

    python3 scripts/pack-industry-app.py examples/taskboard -o /tmp/taskboard-1.0.0.zip

打开 MyCowork 的“工作台”，点击“安装 ZIP”，选择该文件。阅读 Python 代码信任提示并确认。安装后打开应用卡片，点击“重启后端以应用变更”，即可使用页面。

开发 Python 接口时保持 backend/mcapp_cn_example_taskboard 为唯一顶层包名。页面资源放在 frontend/dist，index.html 使用相对路径加载 JS/CSS。页面只能通过工作台的 postMessage 桥接请求 /api/apps/cn.example.taskboard 下的业务 API。

当前版本支持可信本地 Python、静态页面、独立 SQLite 数据以及声明式 Agent 工具。本样例贡献一个只读“查询任务”工具，可在聊天中使用。Python 第三方依赖、Skills、数据迁移和任意宿主能力还未开放；对应清单字段会被安装器拒绝。
