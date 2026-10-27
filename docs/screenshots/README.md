# README 截图维护

`current/` 对应 0.1.6 源码，采集日期为 2026-10-27。中英文 README 共用同一套截图。

这些图片通过仓库当前 React 组件渲染后截图，不是重新绘制的界面。截图数据为明确的演示数据：不读取个人会话、凭据、业务数据库或用户配置，不调用模型，不执行真实任务。助理与技能目录来自仓库源码；行业页面使用 `examples/taskboard/frontend/dist/` 的原始页面，通过演示桥接读取样例任务。

自动化的成功状态、历史会话和模型配置均为布局展示，不是运行验收记录。每张截图右下角标有「README · 当前源码界面 / 示例数据」。图中日期是演示数据，侧栏当前会话时间由组件生成。

## 启动预览

先按仓库 README 安装 Node 和 Python 依赖。在仓库根目录执行：

```bash
node docs/screenshots/tools/serve.mjs
```

默认仅监听本机 `127.0.0.1:5298`；任务管理样例静态页面使用相邻端口 `5299`。可用环境变量 `README_PREVIEW_PORT` 更改起始端口。两个端口都需要空闲。

打开 `http://127.0.0.1:5298/preview.html?scene=home`。预览的后端地址为保留域名 `https://readme.invalid`，请求由本地演示代码拦截；写操作被拒绝。不要将这套预览部署为正式应用。

| scene | 截图文件 | 采集操作 |
| --- | --- | --- |
| `home` | `current/home.jpg` | 首页 |
| `team` | `current/team.jpg` | 多智能体首页 |
| `workspace` | `current/workspace.jpg` | 示例会话与 Markdown 预览 |
| `assistants` | `current/assistants.jpg` | 助理目录 |
| `skills` | `current/skills.jpg` | 再切换到「内置技能」标签 |
| `automations` | `current/automations.jpg` | 自动化列表 |
| `industry` | `current/industry.jpg` | 任务管理样例页面 |
| `industry` | `current/workbench.jpg` | 点击「返回应用列表」 |
| `models` | `current/models.jpg` | 模型设置，不填写真实密钥 |
| `channels` | `current/channels.jpg` | 渠道设置，不登录账号 |

此外提供 `projects` 场景供核对项目页面。当前 JPEG 均为 1280 × 720 的浏览器视口截图，未改绘、拼接或裁切。页面加载完成后检查文字、样例内容与图片，等待过渡动画结束再截图；不要把空白、加载中或错误页面写入 `current/`。

`current/architecture.svg` 是可直接编辑的架构图源码。更新时核对 Electron 生命周期、FastAPI 产品后端、独立 harness、宿主能力回调、插件信任边界和模型数据流。

## 更新要求

- 功能或导航发生变化时，同时修改中英文 README、预览场景和相关截图。
- 版本、技能目录、模型预设、运行状态等以当前代码为准。预览脚本中的版本标记与示例配置也需要随版本检查。
- 保留演示数据标记；截图不应包含 API Key、真实文件路径、个人历史或扫码登录信息。
- 检查 README 的相对链接、图片引用和 `git diff --check`。
- 旧版截图暂保留供其他文档引用；当前 README 的界面插图只引用 `current/` 下的新截图。
