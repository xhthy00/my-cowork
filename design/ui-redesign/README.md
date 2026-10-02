# 当前实现：参考图浅蓝主题

行业插件铺满：进入已选中的行业应用后，自动隐藏 MyCoWork 导航、任务列表和分栏拖动条；插件占满窗口宽度，顶部仅保留 48px 的返回／应用名称／AI 记录／页面操作栏，为原生窗口按钮留出空间。返回列表后恢复原侧栏宽度与折叠偏好；未保存内容的离开确认仍保留，窗口跨过窄布局断点时插件不重载，宿主任务搜索快捷键不抢占插件输入。28 项相关测试与渲染器生产构建通过。`reference-industry-fullscreen.png` 与 `reference-industry-fullscreen-narrow.png` 使用真实 App 外壳及模拟 MiniERP 页面验证布局，未访问实际插件数据；临时页面和服务已清理。

已将本轮设计落到实际 React 页面：常驻浅蓝侧栏、模式联动的小牛 Logo、居中任务输入区、助理卡片目录。新版规范见 `design-system/mycowork/MASTER.md`。

- `reference-home.png`：单智能体首页实际组件截图。
- `reference-home-workforce.png`：多智能体首页实际组件截图。
- `reference-assistants.png`：新版助理目录实际组件截图。
- `reference-add-menu.png`：聊天框 + 两级菜单与技能搜索。
- `reference-settings.png`：带遮罩的设置弹窗与浅蓝分类栏。
- `reference-split-preview.png`：贴边的侧栏、对话与 Word 预览三栏。
- `reference-split-details.png`：对话与运行详情平面分栏，顶部无空白。
- `reference-skills-alignment.png`：技能页面的侧栏和顶部色块边缘对齐。
- `reference-home-polish.png`：新标语与向上发送箭头。
- `reference-assistant-prompts.png`：助理推荐任务三列布局，已验证点击填入草稿。
- `reference-automation.png`：自动化页单层工具栏与统一边距。
- `reference-skills-clean.png`：技能管理页仅展示已安装与内置技能，目录移至独立商店。
- `reference-skill-store.png`：顶部独立「skill商店」页签，保留搜索、分类与安装。
- `reference-navigation-merged.png`：助理、技能与连接器合并后的侧栏入口，顶部仍保留各功能页签。
- `reference-settings-knowledge.png`、`reference-settings-browser.png`：资料库与浏览器移入设置弹窗。
- `reference-projects-aligned.png`：项目工具栏与独立滚动列表分离，首行卡片完整显示。
- 截图使用隔离的浏览器预览与仓库内置助理数据，未调用真实任务执行接口。
- 侧栏左上显示 MyCoWork 与应用实际版本，左下仅保留设置图标。设置以弹窗打开，保留底层页面与草稿。
- 已检查 375px 窄窗口与深色模式；两级菜单支持真实技能与连接器搜索、附件、模式、专家绑定和技能管理。窄窗口子菜单覆盖父菜单以避免超出屏幕。
- 已验证两套小牛 Logo 的模式切换与输入框聚焦状态；生产构建与 47 项相关交互测试通过，包括 Escape 关闭、焦点恢复和设置入口保持当前页面。
- 本次分栏调整通过 32 项相关测试和渲染器生产构建；实际验证了侧栏拖动后的色块边界、对话／预览拖动和双击重置、深色模式、375px 窄窗口预览与详情切换。截图使用隔离的模拟会话与文档，实际任务数据未被修改。
- 本次标语、推荐任务与自动化布局调整通过 24 项相关测试和渲染器生产构建，检查了 375px 窄窗口与深色模式；自动化搜索和新建表单沿用真实功能。
- 重复标题清理覆盖技能、记忆、助理目录、资料库、浏览器子页和 Hub 外部页标题；保留必要的功能分组、区域标签与操作栏，实际预览检查技能、记忆和浏览器页面，25 项相关测试与生产构建通过。
- 商店拆分通过 16 项技能目录、安装与导航相关测试及生产构建；隔离预览验证商店安装后返回技能页显示新技能，以及 375px 窄窗口无横向溢出。截图中的目录为模拟数据，不执行真实安装。
- 额外严格类型检查仍报告仓库原有错误（MessageContent、KnowledgeView、ScheduleView、McpConnectorsPanel、ModelsPanel；pageTab 迁移类型已在商店拆分时修正）；本轮改动未引入新的报错。

本次导航归并与项目布局修复通过 44 项相关测试及生产构建；实际预览验证设置分类切换、CDP 控件、项目列表独立滚动与 375px 窄窗口搜索。严格类型检查仅余既有 MessageContent、ScheduleView、McpConnectorsPanel、ModelsPanel 报错，本轮顺带修正资料库缺失的 KnowledgeSource 类型导入。预览使用模拟项目与仓库内置助理，未修改实际任务或凭据。

以下为之前的视觉方案存档，浅蓝主题规范优先。

补全记录合并：`reference-question-record-merged.png` 展示问题与答案的紧凑记录卡，原说明可展开，回复气泡不重复显示。`reference-workbench-idle.png` 展示空闲工作台。相关前端及生命周期测试 85 项通过；后台 20 项测试通过，覆盖 SSE 终止／断开时关闭嵌套生成器、释放工作计数，以及真实写入线程取消后仍阻止不安全的更新。测试和截图均使用隔离数据，没有操作实际应用、任务或业务数据。

补全表单已按参考改为底部逐题面板，移除占满消息区的长表单。`reference-compact-question.png` 展示编号选项、题号导航、选中态与提交区。验证覆盖前后切换、答案保留、收起与重新展开、选填跳过、必填校验、失败重试，以及提交后恢复聊天输入框；90 项相关测试和渲染器生产构建通过。实际隔离预览检查了 375px 窄窗口、600px 低高度窗口与深色模式，未执行真实任务。严格类型检查仍为仓库既有的 5 处错误，本次相关组件未增加报错。

---

# MyCowork UI 视觉改版提案

本目录提供静态 UI 切图，用于评审视觉方向。画布为 1440 × 900 CSS 像素，PNG 以 2 倍分辨率导出（2880 × 1800）。

## 切图

- `home.png`：工作区首页
- `workspace.png`：对话与文档预览
- `assistants.png`：办公助手
- `skills.png`：技能
- `models.png`：模型配置

## 设计约束

- 保留现有的顶部导航、侧栏、主工作区、预览区和管理页布局。
- 沿用仓库中的 MyCowork 欢迎形象和现有 Inter / 系统中文字体栈。
- 保留页面的主要功能元素和操作入口；切图中的任务与报告文字为现有界面的静态示例。
- 使用紫蓝色强调主操作，浅紫色表示选中态，白色卡片与细边框建立层次，绿色继续表示已完成状态。

`preview.html` 是可调整的静态视觉稿，不会改变当前应用代码或交互逻辑。

## 当前实现：Logo 配色

- `logo-theme-home.png`：首页效果
- `logo-theme-workspace.png`：工作区效果
- `logo-theme-dark.png`：深色模式效果
- 主操作色取自应用图标的亮紫 `#7D3DF3`；珊瑚粉 `#EC8D75` 与暖黄 `#FDD226` 用于柔和背景和装饰渐变。

## 工作空间菜单归并

- `reference-composer-spaces.png`：真实组件隔离预览，工作空间完整菜单迁移到聊天框底栏，侧栏保留导航与历史。
- 搜索、键盘选择、空白／文件夹创建、取消选目录、重命名、会话归属与禁用状态均经过回归测试。
- 检查桌面与 375px 窄窗口，创建子菜单在窄窗口覆盖父菜单，保留完整选项。

- `reference-settings-schedule-dark.png`：设置弹窗的定时任务深色模式预览，修复固定白色工具栏及表单背景；已核对浅色模式、深色模式和新建表单，22 项相关测试与渲染构建通过。
