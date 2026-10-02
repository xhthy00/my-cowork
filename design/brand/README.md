# MyCoWork 蓝色 3D Logo

当前启动页按用户最新要求移除上方独立小牛与眨眼效果，仅居中展示蓝色横版 Logo、启动提示和加载进度条；横版入场／悬浮动画、深色适配与失败重试保留。下文小牛启动页截图与眨眼说明为历史记录。

采用用户确认的 `mycowork-3d-blue-v1.png`；`renderer/src/assets/brand/app-logo.png` 与设计稿逐字节一致。原设计提示词保存在 `mycowork-3d-blue-v1-prompt.md`。

启动页、标题栏、折叠侧栏与网页 favicon 共用新资产。启动页沿用原布局，文字、光晕与进度条改为蓝白主题，并适配深色模式与减少动态效果的偏好。

`python3 build/generate-icon.py` 从主图导出 `build/icon.png`（1024px）、`build/icon.ico`（16、24、32、48、64、128、256px）和 `docs/screenshots/app-icon.png`（512px）。macOS 开发模式启动窗口时同步更新 Dock 图标；安装包图标通过现有打包配置使用新资源，已安装版本需要重新打包安装后更新。

验证：桌面程序与渲染器构建通过，19 项侧栏与聊天输入测试通过；确认透明通道、ICO 尺寸与源图一致性，实际检查浅色启动页、深色 375px 窄窗口和首页。

- `startup-blue-3d.png`：实际启动页。
- `startup-blue-3d-dark-narrow.png`：深色窄窗口。
- `home-blue-3d.png`：此前使用应用图标的首页存档。

## 按模式切换的新建聊天插图

按照原有场景逻辑，以新版蓝灰色 3D 小牛为角色参考，通过内置 image_gen 编辑生成两张透明背景插图。单智能体保留一只小牛陪伴与上下两行品牌字样；多智能体保留四只小牛一起使用电脑、记笔记的协作场景与一行品牌字样。花朵、星星和字样采用浅蓝、湖蓝配色，保留少量柔粉色与自然绿叶。

- 单智能体原稿：`welcome-single-blue.png`；最终提示词：`welcome-single-blue-prompt.md`。
- 多智能体原稿：`welcome-workforce-blue.png`；最终提示词：`welcome-team-blue-prompt.md`。
- 页面资源：`renderer/src/assets/welcome/chat-welcome-hero-blue.webp` 与 `chat-welcome-hero-workforce-blue.webp`，均为 1200 × 800 RGBA WebP。
- 页面预览：`welcome-single-page.png`、`welcome-workforce-page.png`、`welcome-workforce-dark-page.png`。

ChatView 订阅现有 sessionMode，点击输入区的会话模式按钮后同步切换对应插图。原版插图保留。验证：渲染器生产构建通过，聊天输入与会话状态的 61 项现有测试通过；实际页面确认两种模式切图、草稿保留及浅色/深色背景下的透明效果。

预览使用临时隔离页面与模拟 IPC，未读取或修改真实任务、业务数据和凭据；临时页面及预览服务已清理。

## 启动页横版标识恢复

原横版标识在替换蓝色小牛时被普通文字替代。已通过内置 image_gen 编辑原 `logo-horizontal.png`，保留立体斜体字形、小牛替代字母 o 的结构与「AI 让办公更智能」标语，配色改为湖蓝、冰蓝与蓝灰。新版透明资产为 `renderer/src/assets/brand/logo-horizontal-blue.png`；原始横版资产保留，最终提示词见 `logo-horizontal-blue-prompt.md`。

启动页恢复横版图片，保留 0.9 秒延迟入场、3 秒轻微悬浮、小牛入场与进度条动画；深色模式提高字标亮度，减少动态效果时静态显示全部内容。已检查 1440px 浅色画布、375px 深色窄窗口、减少动态 CSS 规则生效后的可见性，以及模拟启动失败状态。渲染器生产构建通过。

- `startup-horizontal-blue.png`：新版实际启动页。
- `startup-horizontal-blue-dark-narrow.png`：新版深色窄窗口。

本次预览同样使用隔离页面与模拟 IPC；未调用真实后端启动或重试接口，临时预览页面与服务已清理。

## 蓝色小牛眨眼恢复

用户指出启动页顶部原本使用 `cow-blink.webp` 眨眼动画；此前只保留了图标入场与横版标识悬浮，遗漏了眨眼。现在以当前蓝色 `app-logo.png` 为睁眼帧，通过内置 image_gen 生成 `cow-blink-blue-closed.png` 闭眼帧，仅在眼部遮罩区域循环切换，每 3.8 秒眨眼两次。方形底板、小牛头部与嘴巴始终使用睁眼原图，避免图标位移；减少动态偏好下关闭眨眼并保持睁眼。

最终提示词见 `cow-blink-blue-prompt.md`，原紫橙色 WebP 保留。已核对睁眼／闭眼定位、循环动画 CSS、1440px 浅色与 375px 深色效果、减少动态规则生效后的静态睁眼状态；渲染器生产构建通过。预览仍使用模拟 IPC，临时文件和服务已清理。

- `startup-cow-blink-closed.png`：实际组件闭眼瞬间。
- `startup-cow-blink-dark-narrow.png`：深色窄窗口闭眼瞬间。
