<p align="center">
  <img src="./renderer/src/assets/brand/app-logo.png" width="96" alt="MyCowork" />
</p>

<h1 align="center">MyCowork</h1>

<p align="center">
  <strong>本机办公数字员工，也能进入你的业务工作台</strong><br />
  文件交付 · 单 / 多智能体 · 技能与连接器 · 自动化 · 行业应用
</p>

<p align="center">Electron · React · FastAPI · Deep Agents · OfficeCLI</p>
<p align="center"><strong>中文</strong> · <a href="./README.en.md">English</a></p>

MyCowork 是面向 macOS 和 Windows 的桌面办公 Agent。描述任务、选择工作空间，助手可以使用本机文件和工具，生成 Word、Excel、PPT、PDF、Markdown 等交付物，并在同一窗口中查看结果。通过行业工作台，还可以把业务页面、数据和 AI 工具装进同一个桌面应用。

任务执行与数据存储以本机为中心；模型可接云服务或本地推理服务。**使用云模型时，任务中交给模型的内容会发送到所配置的服务端**，并非所有内容都留在本机。

本文按 **0.1.6 当前源码**整理（2026-10-27）。截图使用真实界面组件与隔离示例数据；示例会话、自动化记录和模型配置不代表实际执行或连接结果。截图维护方式见 [截图说明](docs/screenshots/README.md)。

## 界面与主要功能

从「新建任务」选择模型和工作空间开始，侧栏集中管理项目、任务、助理、自动化和工作台。

![当前版本首页](docs/screenshots/current/home.jpg)

| 能力 | 当前支持 |
| --- | --- |
| 任务与项目 | 工作空间、项目与会话管理，历史记录、任务步骤、运行详情、交付文件和预览 |
| 单 / 多智能体 | 单智能体直接处理任务；多智能体通过 Deep Agents 子代理委派文档、浏览、开发等工作，复杂任务可先确认计划 |
| 办公助理 | 10 位场景助理，覆盖文档、演示、表格、公文、财务建模、法务和跨格式协作 |
| 技能与记忆 | 本机技能、内置技能、技能商店、智能体访问范围；技能按需加载，长期记忆可管理 |
| 连接器与浏览器 | MCP 工具连接、浏览器页面读取与操作、文件上传和截图 |
| 自动化 | 可视化创建计划、立即运行、暂停、查看运行记录、配置权限和处理恢复审核 |
| 行业工作台 | 安装带独立页面、Python 业务后端、Agent 工具和随包技能的 ZIP 应用 |
| 远程连接 | 飞书官方长连接、微信 ClawBot 扫码接入；Telegram 和钉钉目前标为「即将推出」 |

### 对话、交付和预览

任务结果可以保存为工作空间中的真实文件。文件卡片、运行详情与预览面板帮助你检查交付结果，并继续修改。下图以 Markdown 周报展示对话与预览布局。

![对话与交付文件预览](docs/screenshots/current/workspace.jpg)

办公文档优先使用捆绑的 [OfficeCLI](https://github.com/iOfficeAI/OfficeCLI) 生成和预览；仓库也包含 `python-docx`、`python-pptx`、`openpyxl` 等文档工具。具体格式和预览效果取决于所用工具及运行环境。

多智能体模式从同一输入框切换。底层使用官方 `create_deep_agent()` 与子代理机制，产品层提供计划确认、权限审批、任务状态和产物登记。

<details>
<summary>查看多智能体入口</summary>

![多智能体模式入口](docs/screenshots/current/team.jpg)

</details>

### 办公助理、技能与连接器

「助理 · 技能 · 连接器」集中提供场景助理、技能开关、技能商店、记忆和 MCP 连接器。选择助理可以带入对应技能和建议提问。

![当前办公助理目录](docs/screenshots/current/assistants.jpg)

| 分类 | 助理 | 典型用途 |
| --- | --- | --- |
| 演示文稿 | PPT 演示、路演 PPT | 业务汇报、培训、融资路演 |
| 文档 | Word 文档、公文写作、Word 表单 | 周报方案、公文草稿、填写表单 |
| 表格 | Excel 表格、数据仪表盘、财务建模 | 台账、KPI 看板、预测模型 |
| 法务 | 中国法务顾问 | 合同审查、起草、风险与依据整理 |
| 通用 | 办公协作 | 同一任务组合交付 PPT、Word、Excel |

公文和法务助理用于辅助撰写、检查与分析；正式发文、合同与重大事项需要人工复核。

<details>
<summary>查看内置技能管理</summary>

![内置技能及访问权限](docs/screenshots/current/skills.jpg)

</details>

### 行业工作台

在侧栏「工作台」安装 ZIP，即可使用带业务页面的行业应用。宿主检查包结构、兼容版本和文件校验值；安装或更新会等待当前工作结束，保存数据恢复点并重新加载应用。

![行业工作台应用列表](docs/screenshots/current/workbench.jpg)

应用可以贡献业务工具和技能。页面通过受控桥接传递选中业务内容、发起 AI 任务、查看记录与交付文件，并按结果返回业务页面。仓库内的任务管理样例演示了风险分析、周报生成和子任务拆分入口。

![任务管理样例业务页面](docs/screenshots/current/industry.jpg)

当前插件是 **Python 后端 + 静态 Web 页面**。Python 插件在宿主后端进程中运行，安装器不会为其创建独立虚拟环境或执行 `pip` / `npm`。页面桥接限制不等于 Python 代码隔离，因此应安装来源可信的应用。

开发入口：[行业应用插件开发指南](docs/行业应用插件开发指南.md) · [任务管理样例](examples/taskboard/README.md)。

### 自动化

在侧栏「自动化」配置任务内容、计划、工作空间与允许使用的工具，查看每次运行的结果和状态。支持立即执行、暂停、完成通知以及中断后的恢复审核。

![自动化任务列表](docs/screenshots/current/automations.jpg)

计划由本机执行，需要电脑保持唤醒且后端运行。重新启动后会对错过的计划补执行一次；涉及不确定副作用的恢复可能需要人工审核。应用内可打开「保持唤醒」。

### 模型与远程连接

模型设置位于左下角 **设置 → 模型**。支持 Anthropic、OpenAI、OpenRouter、DeepSeek、通义千问、Moonshot、MiniMax、自定义兼容服务，以及 Ollama、LM Studio、vLLM 等本地服务。填写服务地址、模型 ID 和所需密钥，验证通过后保存。

![模型设置](docs/screenshots/current/models.jpg)

**设置 → 远程连接**提供飞书和微信入口。飞书使用官方长连接，微信通过 ClawBot 扫码登录，这两种入口无需配置公网 URL 或 Cloudflare Tunnel。电脑休眠或退出应用后，远程任务不能持续执行。

![远程连接及渠道状态](docs/screenshots/current/channels.jpg)

## 快速开始

### 安装使用

从 [GitHub Releases](https://github.com/xhthy00/my-cowork/releases) 获取对应平台安装包：macOS 为 `.dmg`，Windows 为 NSIS `.exe`。

1. 打开应用，在 **设置 → 模型** 配置服务；使用本地模型时，先启动相应推理服务。
2. 在「新建任务」选择工作空间与模型，或从办公助理开始。
3. 输入任务；出现权限请求时核对操作、路径和命令，然后查看交付文件。

可用以下任务检查文件交付：

> 在当前工作空间创建 hello.md，写入一段欢迎文字，完成后提供文件预览。

### 从源码运行

建议环境：**Node.js 22 LTS、Python 3.11 或 3.12、[uv](https://docs.astral.sh/uv/)**，以及 macOS 或 Windows。以下命令在仓库根目录执行：

```bash
uv sync --project backend --locked --extra dev
npm ci

# 下载办公文档工具（Windows 请在 Git Bash 中执行）
npm run fetch:officecli

# 源码开发首次使用内置浏览器时安装 Chromium
uv run --project backend python -m playwright install chromium

npm run dev
```

`npm run dev` 启动 Vite（默认 `127.0.0.1:5174`），编译 Electron 并启动桌面应用。**Electron 管理 Python 后端和 Agent sidecar 的启动与退出**，正常开发流程无需另外手动运行 Uvicorn。`fetch:officecli` 需要 Bash；Windows 可安装 Git for Windows 并在 Git Bash 中执行。安装使用说明见 [部署手册](docs/部署手册.md)。

### 检查与打包

```bash
# 后端测试与依赖边界检查
cd backend
uv run --locked --extra dev pytest -q
uv run --locked --extra dev lint-imports
cd ..

# 前端 / Electron 单元测试；E2E 命令内含构建
npm test
npm run test:e2e

# 预览云端打包或版本发布计划，不执行推送
npm run package:ci -- --dry-run
npm run release -- --dry-run
```

云端构建配置位于 [build.yml](.github/workflows/build.yml)。本地 Windows 可用 `npm run package:win`，全量构建使用 `npm run package:win:full`；macOS 可用 `npm run build:python:mac` 后执行 `bash scripts/build-electron.sh --mac`。实际发布要求工作区干净并具有 Git 推送权限；`package:ci` 还需要已登录的 GitHub CLI。命令会执行推送或发布，先用 `--dry-run` 检查计划。

行业应用开发可从脚手架开始：

```bash
npm run app -- init /path/to/my-app --id cn.example.myapp --name 我的业务应用
npm --prefix /path/to/my-app/frontend install
npm run app -- dev /path/to/my-app
npm run app -- pack /path/to/my-app -o /path/to/my-app.zip
```

`dev` 使用隔离的开发数据与凭据范围；正式安装包通过工作台的「安装 ZIP」加载。

## 架构与数据边界

![当前桌面应用与 Agent 运行架构](docs/screenshots/current/architecture.svg)

Electron 主进程负责桌面能力、凭据与进程管理，React 界面通过宿主访问本机 FastAPI。产品后端管理任务、权限、业务数据和工具；独立 `cowork_harness` sidecar 承接官方 Deep Agents 执行，通过宿主能力回调使用文件、命令、浏览器、MCP 和行业工具。

| 模块 | 职责 |
| --- | --- |
| `renderer/`、`electron/` | 页面、文件预览、IPC、凭据与进程生命周期 |
| `backend/app/orchestrator/` | 产品任务、入口上下文、事件和产物 |
| `backend/cowork_harness/` | Deep Agents 工厂、子代理、checkpoint、持久中断、事件与预算 |
| `backend/runtime_contract/`、`app/runtime_client/` | 版本化协议、sidecar 启动与构建兼容性检查 |
| `backend/app/host_capabilities/` | 工具回调、任务权限范围、审批票据与副作用去重 |
| `backend/model_integrations/` | 宿主与 harness 共享的模型适配 |
| `backend/app/industry_apps/`、`automation/`、`server/channels/` | 行业应用、计划运行和远程渠道 |

后端和 sidecar 共用 Python 环境、`backend/pyproject.toml` 与 `backend/uv.lock`。当前锁定 Deep Agents 0.7.23；由官方图管理工具循环、子代理和上下文压缩，产品保留授权与交付流程。实施细节见 [Deep Agents 实施说明](docs/DeepAgents实施说明.md)。

- **本机数据**：会话、记忆、计划与运行记录存储在本机；交付文件写入任务对应的工作目录。实际目录以工作空间和设置为准。
- **模型与外部工具**：云模型、MCP、远程渠道与知识服务可能把相关内容发送到外部服务；本地模型也需要你另行部署推理服务。
- **凭据**：桌面端在系统安全存储可用时使用 Electron `safeStorage` 加密凭据文件；不可用且没有既有加密文件时，当前实现可退回受文件权限保护的本机 JSON，不能承诺始终存于系统钥匙串。
- **权限**：文件白名单、工作目录限制、命令策略与操作审批共同约束宿主工具；后端默认路径范围包含用户主目录，可在「隐私 / 白名单」中收紧。这些是应用层控制，不是操作系统沙箱。
- **运行条件**：自动化、远程连接和行业任务依赖本机应用与后端；当前不是独立的云端常驻服务。

## 仓库与文档

```text
backend/                   产品后端、独立 harness、共享运行协议与测试
electron/                  桌面主进程与预加载桥接
renderer/                  React 界面与样式
packages/app-sdk/          行业应用前端 SDK
templates/industry-app/    行业应用脚手架
examples/taskboard/        可运行的行业应用样例
skills/                    仓库技能
resources/example-skills/ 内置与第三方技能
scripts/、build/           开发、依赖获取、打包与发布
docs/                      实施、开发、部署文档与截图
```

- [开发指南](docs/开发指南.md)：本地开发、Skill、MCP 与办公助理。
- [部署手册](docs/部署手册.md)：安装、依赖、配置与打包；远程入口以本文及当前「远程连接」界面为准。
- [Deep Agents 实施说明](docs/DeepAgents实施说明.md)：运行架构、协议、权限与验证。
- [行业应用插件开发指南](docs/行业应用插件开发指南.md)：包规范、SDK、工具、业务 AI 与生命周期。
- [技能说明](skills/README.md) · [截图维护说明](docs/screenshots/README.md)。

## 协议

本仓库以 [MIT License](LICENSE) 发布。`resources/example-skills/` 中捆绑的第三方技能保留各自目录内的原始协议。
