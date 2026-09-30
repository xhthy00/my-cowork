#!/usr/bin/env python3
"""Build the HyperFrames composition from the real UI capture manifest."""

from __future__ import annotations

import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
clips = json.loads((ROOT / "live_clips.json").read_text())
total_live = round(sum(clip["duration"] for clip in clips), 1)
total = round(total_live + 2, 1)

groups = []
current_label = None
position = 0.0
for idx, clip in enumerate(clips):
    start = round(position, 1)
    duration = clip["duration"]
    if clip["label"] != current_label:
        groups.append({"label": clip["label"], "caption": clip["caption"], "start": start, "end": None})
        if len(groups) > 1:
            groups[-2]["end"] = start
        current_label = clip["label"]
    position = round(position + duration, 1)
groups[-1]["end"] = total_live

labels = []
for idx, group in enumerate(groups):
    labels.append(
        f'    <div id="label-{idx}" class="rail-label" aria-hidden="true">'
        f'<span class="rail-label-en">{idx + 1:02d} / MYCOWORK</span>'
        f'<strong>{html.escape(group["label"])}</strong>'
        f'<span class="rail-label-caption">{html.escape(group["caption"])}</span></div>'
    )

timeline = []
for idx, group in enumerate(groups):
    start = group["start"]
    end = group["end"]
    timeline.append(f'    tl.to("#label-{idx}", {{ opacity: 1, duration: .28, ease: "sine.out" }}, {start:.1f});')
    timeline.append(f'    tl.to("#label-{idx}", {{ opacity: 0, duration: .18, ease: "sine.in" }}, {max(start + .4, end - .18):.1f});')
for idx, clip in enumerate(clips[1:], 1):
    start = round(sum(item["duration"] for item in clips[:idx]), 1)
    timeline.append(f'    tl.to("#cut-flash", {{ opacity: .22, duration: .08, ease: "none" }}, {max(0, start - .06):.1f});')
    timeline.append(f'    tl.to("#cut-flash", {{ opacity: 0, duration: .20, ease: "sine.out" }}, {start + .02:.2f});')

document = f'''<!doctype html>
<html lang="zh-CN" data-resolution="landscape">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=1920, height=1080">
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>
    @font-face {{ font-family: "PingFang SC"; src: local("PingFang SC"); }}
    @font-face {{ font-family: "Microsoft YaHei"; src: local("Microsoft YaHei"); }}
    * {{ box-sizing: border-box; }}
    html, body {{ width: 1920px; height: 1080px; margin: 0; overflow: hidden; }}
    body {{ font-family: "PingFang SC", "Microsoft YaHei", sans-serif; color: #33223f; background: #f9f4fd; }}
    #root {{ position: relative; width: 1920px; height: 1080px; overflow: hidden; }}
    #screen-stage {{ position: absolute; inset: 0; z-index: 1; }}
    .capture {{ position: absolute; left: 99px; top: 0; width: 1722px; height: 1080px; object-fit: contain; background: #fff; }}
    .rail {{ position: absolute; top: 0; bottom: 0; width: 99px; z-index: 3; overflow: hidden; background: linear-gradient(180deg, #fbf6ff, #f0e5fa); }}
    #rail-left {{ left: 0; border-right: 1px solid #e4d1f1; }}
    #rail-right {{ right: 0; border-left: 1px solid #e4d1f1; }}
    .rail .brand {{ position: absolute; top: 28px; left: 25px; writing-mode: vertical-rl; color: #6b27c9; font-size: 17px; font-weight: 900; letter-spacing: .16em; }}
    .rail .version {{ position: absolute; bottom: 33px; left: 38px; writing-mode: vertical-rl; color: #65516f; font-size: 15px; font-weight: 700; letter-spacing: .05em; }}
    .rail-label {{ position: absolute; top: 190px; left: 17px; width: 64px; height: 640px; opacity: 0; display: flex; flex-direction: column; gap: 24px; align-items: center; }}
    .rail-label-en, .rail-label-caption {{ color: #65516f; font-size: 13px; font-weight: 700; writing-mode: vertical-rl; letter-spacing: .08em; }}
    .rail-label strong {{ color: #6f2bd3; font-size: 26px; font-weight: 900; writing-mode: vertical-rl; letter-spacing: .13em; }}
    #rail-right .dot {{ position: absolute; top: 39px; left: 41px; width: 17px; height: 17px; background: #7d3df3; border-radius: 50%; box-shadow: 0 0 0 7px rgba(125,61,243,.13); }}
    #rail-right .copy {{ position: absolute; top: 109px; left: 38px; writing-mode: vertical-rl; color: #6a527a; font-size: 15px; font-weight: 700; letter-spacing: .14em; }}
    #rail-right .progress-track {{ position: absolute; top: 470px; bottom: 70px; left: 47px; width: 5px; border-radius: 99px; background: #e5d4ef; }}
    #rail-right .progress-fill {{ position: absolute; inset: 0; border-radius: inherit; background: #7d3df3; transform-origin: top; }}
    #cut-flash {{ position: absolute; left: 99px; top: 0; width: 1722px; height: 1080px; z-index: 2; background: #fff; opacity: 0; pointer-events: none; }}
    #outro {{ position: absolute; inset: 0; z-index: 5; opacity: 0; background: radial-gradient(circle at 51% 40%, #fff 0%, #f7eefc 68%, #f1e4fa 100%); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 25px; text-align: center; }}
    #outro img {{ width: 560px; height: auto; }}
    #outro h1 {{ margin: 0; max-width: 1500px; color: #302238; font-size: 74px; font-weight: 900; letter-spacing: -.04em; }}
    #outro p {{ margin: 0; color: #765b8b; font-size: 29px; }}
    #outro .version {{ color: #6b27c9; font-size: 22px; font-weight: 800; letter-spacing: .08em; }}
  </style>
</head>
<body>
  <div id="root" data-composition-id="main" data-start="0" data-duration="{total:.1f}" data-width="1920" data-height="1080" data-fps="30">
    <div id="screen-stage" data-layout-allow-overlap>
      <video id="live-demo" class="clip capture" data-start="0" data-duration="{total_live:.1f}" data-track-index="0" src="assets/live-demo.mp4" muted playsinline aria-label="MyCowork 桌面客户端真实操作录制"></video>
    </div>
    <div id="cut-flash" data-layout-allow-overlap></div>
    <aside id="rail-left" class="rail" data-layout-allow-overlap>
      <div class="brand">MYCOWORK</div>
{chr(10).join(labels)}
      <div class="version">VERSION 0.1.1 · REAL UI</div>
    </aside>
    <aside id="rail-right" class="rail" data-layout-allow-overlap>
      <div class="dot"></div><div class="copy">桌面客户端 · 真实操作录制</div>
      <div class="progress-track"><div class="progress-fill"></div></div>
    </aside>
    <div id="outro" data-layout-allow-overlap>
      <img src="assets/logo-end.png" alt="MyCowork 品牌标识">
      <h1>应用、智能体与知识，在一个工作区</h1>
      <p>MyCowork · 真实桌面操作</p>
      <div class="version">RELEASE 0.1.1</div>
    </div>
    <audio id="score" class="clip" data-start="0" data-duration="{total:.1f}" data-track-index="2" data-volume="0.72" src="assets/score-live.m4a"></audio>
  </div>
  <script>
    window.__timelines = window.__timelines || {{}};
    const tl = gsap.timeline({{ paused: true }});
    tl.fromTo(".progress-fill", {{ scaleY: 0 }}, {{ scaleY: 1, duration: {total_live:.1f}, ease: "none" }}, 0);
{chr(10).join(timeline)}
    tl.to("#outro", {{ opacity: 1, duration: .50, ease: "sine.inOut" }}, {total_live - .1:.1f});
    tl.from("#outro img", {{ opacity: 0, y: 24, duration: .5, ease: "power2.out" }}, {total_live + .1:.1f});
    tl.from("#outro h1", {{ opacity: 0, y: 20, duration: .5, ease: "power2.out" }}, {total_live + .3:.1f});
    tl.from("#outro p, #outro .version", {{ opacity: 0, y: 12, duration: .4, stagger: .12, ease: "sine.out" }}, {total_live + .5:.1f});
    window.__timelines["main"] = tl;
  </script>
</body>
</html>
'''
(ROOT / "index.html").write_text(document)
print(f"Built {len(clips)} real-operation clips; live {total_live:.1f}s, total {total:.1f}s")
