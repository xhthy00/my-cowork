#!/usr/bin/env python3
"""Encode real MyCowork UI captures into editable HyperFrames media clips."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FFMPEG = Path("/Applications/MiniMax Design.app/Contents/Resources/ffmpeg/ffmpeg")
FPS = 10
CLIPS = [
    ("workbench-tab", 31, "行业工作台", "从主页进入行业应用"),
    ("task-open", 29, "行业工作台", "打开任务与工时"),
    ("task-list-open", 26, "任务管理", "查看分层任务"),
    ("task-expand", 24, "任务管理", "展开父任务"),
    ("task-detail-open", 27, "任务管理", "查看子任务进度"),
    ("task-worklog-open", 28, "工时记录", "查看工作记录"),
    ("task-map-open", 30, "任务导图", "打开可交互导图"),
    ("task-map-collapse", 24, "任务导图", "收起子任务"),
    ("task-map-expand", 22, "任务导图", "展开子任务"),
    ("task-map-pan", 27, "任务导图", "鼠标拖动画布"),
    ("task-stats-open", 29, "工时统计", "查看真实统计数据"),
    ("answer-scroll-up", 32, "单智能体", "滚动查看助手回答"),
    ("report-open", 34, "报告交付", "打开生成的 HTML 报告"),
    ("report-scroll", 35, "报告交付", "阅读报告正文"),
    ("mode-menu", 28, "多智能体", "切换会话模式"),
    ("multi-run-start", 60, "多智能体", "提交任务并查看分工"),
    ("multi-run-progress", 50, "多智能体", "实时查看协作步骤"),
    ("knowledge-open", 30, "知识库", "进入知识源配置"),
]


def main() -> None:
    out_dir = ROOT / "assets" / "live-clips"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, count, label, caption in CLIPS:
        input_pattern = ROOT / "assets" / "live" / name / "%03d.png"
        missing = [i for i in range(count) if not (ROOT / "assets" / "live" / name / f"{i:03d}.png").exists()]
        if missing:
            raise FileNotFoundError(f"{name}: missing capture frames {missing}")
        output = out_dir / f"{name}.mp4"
        subprocess.run(
            [
                str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
                "-framerate", str(FPS), "-f", "image2", "-c:v", "mjpeg",
                "-start_number", "0", "-i", str(input_pattern),
                "-t", str(count / FPS), "-vf",
                "scale=1722:1080:force_original_aspect_ratio=decrease:flags=lanczos,"
                "pad=1722:1080:(ow-iw)/2:(oh-ih)/2:color=white,fps=30",
                "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(output),
            ],
            check=True,
        )
        manifest.append({"name": name, "file": f"assets/live-clips/{name}.mp4", "duration": count / FPS, "label": label, "caption": caption})
        print(f"{name}: {count / FPS:.1f}s")
    (ROOT / "live_clips.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    concat_file = out_dir / "concat.txt"
    concat_file.write_text("".join(f"file '{(out_dir / (clip['name'] + '.mp4')).as_posix()}'\n" for clip in manifest))
    subprocess.run(
        [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-r", "30", "-g", "30", "-keyint_min", "30", "-sc_threshold", "0", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(ROOT / "assets" / "live-demo.mp4")],
        check=True,
    )
    print(f"live-demo: {sum(clip['duration'] for clip in manifest):.1f}s")


if __name__ == "__main__":
    main()
