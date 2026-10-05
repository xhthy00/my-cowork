# MyCoWork 统一推广文章

使用同一个标题和正文，发布到 CSDN、掘金、知乎等平台。

**标题：开源了！给业务装上 AI 团队：MyCoWork 的多智能体与行业工作台**

[打开完整文章](MyCoWork统一推广文章.md)

[打开图文 HTML 预览](MyCoWork图文推广文章.html)

[下载完整图文素材 ZIP](MyCoWork推广图文素材.zip)

正文严格按“技术栈 → 功能点 → 重点功能：行业工作台”递进。行业工作台占据主要篇幅，展开业务页面、上下文、工具操作、随包技能和开发流程，以当前仓库实现为依据。文章采用项目作者口吻，可直接复制到各平台编辑器。

## 统一摘要

MyCoWork 是 MIT 开源的桌面办公 Agent，支持 Word、Excel、PPT 文件生成，提供单智能体与多智能体协同，并通过行业工作台连接业务页面、数据和 AI 工具。本文从技术栈与整体功能入手，重点介绍行业工作台如何连接业务页面、数据、场景技能和 AI 工具。

## 配图

正文已插入 7 张配图：品牌封面、架构图、多智能体流程图、行业工作台流程图，以及当前单智能体首页、多智能体首页和任务管理行业应用界面。结构图使用项目浅蓝色与原有 Logo，提供 PNG 和可编辑 SVG；界面图保留原组件视觉。

| 文件 | 用途 |
| --- | --- |
| [01-cover.png](images/01-cover.png) | 1600 × 900 品牌封面 |
| [02-architecture.png](images/02-architecture.png) | 桌面、后端、工具与模型架构 |
| [03-workforce.png](images/03-workforce.png) | 多智能体计划、依赖、分工与重试 |
| [04-industry-workbench.png](images/04-industry-workbench.png) | 行业包组成与业务 AI 链路 |
| [05-ui-home.png](images/05-ui-home.png) | 当前单智能体首页 |
| [06-ui-industry.png](images/06-ui-industry.png) | 当前任务管理插件页面与宿主 |
| [07-ui-team.png](images/07-ui-team.png) | 当前多智能体模式首页 |
| [mycowork-logo.png](images/mycowork-logo.png) | 512 × 512 原有小牛 Logo |

界面图来自当前源码组件及原任务管理样例的隔离预览，使用内存演示数据与模型显示配置，没有执行真实模型任务、访问日常实例或读写实际业务数据。已在图片底部和正文图注注明，不能用作模型效果或性能证据。未使用模拟 MiniERP 图。

各平台使用同一正文，上传对应 PNG 替换本地图片引用。SVG 保留为后续编辑源文件；所有结构图均为示意图。

## 素材再生成

图形源代码为 `tools/render-figures.mjs`，使用 sharp 渲染 SVG 为 PNG。环境中已有 sharp 时直接执行；否则将 `PROMOTION_NODE_MODULES` 指向包含该依赖的模块目录。脚本复用仓库原有图标与团队插图，不修改原资产。

HTML 预览通过 `node docs/promotion/tools/render-article.mjs` 生成。界面截图的隔离数据配置保存在 `tools/capture-preview.tsx`；截图时使用临时 Vite 入口和任务样例页面服务，完成后移除临时入口并关闭服务。

## 核对依据

- [项目 README](../../README.md)
- [行业应用开发指南](../行业应用插件开发指南.md)
- [任务管理样例](../../examples/taskboard/README.md)
- [Workforce 实现](../../backend/app/graphs/workforce.py)
- [运行入口](../../backend/app/runtime/graph_runner.py)
- [项目许可](../../LICENSE)

内容基于 2026-10-02 当前仓库实现。发布配图与体验版本应对应实际支持的能力。
