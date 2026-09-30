# MyCowork v0.1.1 真实操作宣传视频

本版以桌面客户端的实际鼠标操作和页面变化为主体，连续展示行业工作台、分层任务、工时记录、任务导图、单智能体回答与报告、多智能体执行以及知识库配置。窗口完整等比呈现，不裁切。

- 动态成片：`renders/MyCowork-v0.1.1-live-demo.mp4`（58.6 秒，1920 × 1080，30 fps）
- HyperFrames 合成源：`index.html`
- 原始操作帧：`assets/live/`
- 分段媒体与顺序：`assets/live-clips/`、`live_clips.json`
- 分段编码：`python3 build_live_clips.py`
- 合成 HTML：`python3 build_composition.py`
- 分镜及边界：`SCRIPT.md`、`SOURCES.md`、`DESIGN.md`

旧版静态剪辑仍保留在 `renders/MyCowork-v0.1.1-promo.mp4`，便于对比。使用 Node.js 22+、FFmpeg/FFprobe 与 HyperFrames CLI 在本目录运行 `npm run check`、`npm run render` 可检查并重渲染。
