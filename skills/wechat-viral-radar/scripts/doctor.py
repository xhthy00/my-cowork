import json
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def check_file(path: Path) -> tuple[bool, str]:
    return path.exists(), str(path.relative_to(ROOT))


def check_network() -> tuple[bool, str]:
    try:
        req = urllib.request.Request(
            "https://weixin.sogou.com/",
            headers={"User-Agent": "Mozilla/5.0 WeChatViralRadar/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status < 500, f"HTTP {resp.status}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    print("WeChat Viral Radar doctor")
    print(f"Python: {sys.version.split()[0]}")
    required = [
        ROOT / "SKILL.md",
        ROOT / "agents" / "openai.yaml",
        ROOT / "references" / "tracks.json",
        ROOT / "scripts" / "wechat_viral_radar.py",
    ]
    ok = True
    for path in required:
        exists, label = check_file(path)
        print(f"{'OK' if exists else 'MISSING'} {label}")
        ok = ok and exists

    tracks_path = ROOT / "references" / "tracks.json"
    if tracks_path.exists():
        try:
            data = json.loads(tracks_path.read_text(encoding="utf-8"))
            print(f"OK tracks: {len(data)}")
        except Exception as exc:
            print(f"BAD tracks.json: {exc}")
            ok = False

    live_ok, live_msg = check_network()
    print(f"{'OK' if live_ok else 'WARN'} public source check: {live_msg}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

