import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str]) -> int:
    print("+", " ".join(args))
    proc = subprocess.run(args, cwd=ROOT, text=True)
    return proc.returncode


def main() -> int:
    required = [
        "SKILL.md",
        "agents/openai.yaml",
        "references/tracks.json",
        "references/public_sources.md",
        "references/faq.md",
        "references/parameters.md",
        "references/chat_only_workflow.md",
        "examples/workflows.md",
        "examples/full_report_sample.md",
        "scripts/start.py",
        "scripts/wechat_viral_radar.py",
        "scripts/doctor.py",
    ]
    missing = [name for name in required if not (ROOT / name).exists()]
    if missing:
        print("Missing files:")
        for name in missing:
            print("-", name)
        return 1

    if run([sys.executable, "scripts/doctor.py"]) != 0:
        return 1
    if run([sys.executable, "scripts/start.py", "--track", "ai", "--limit", "3", "--demo", "--report-style", "deep", "--ideas-per-article", "3", "--output-dir", "examples/verify_output"]) != 0:
        return 1
    if run([sys.executable, "scripts/start.py", "--track", "ai", "--limit", "2", "--simulate-blocked", "--output-dir", "examples/verify_fallback"]) != 0:
        return 1

    report = ROOT / "examples" / "verify_output" / "wechat_viral_report.md"
    fallback_report = ROOT / "examples" / "verify_fallback" / "wechat_viral_report.md"
    fallback_csv = ROOT / "examples" / "verify_fallback" / "manual_fallback_queries.csv"
    report_text = report.read_text(encoding="utf-8-sig") if report.exists() else ""
    required_sections = [
        "Article Candidates",
        "Confidence Notes",
        "Audience Pain Points",
        "Creative Angle Bank",
        "3-Day Publishing Plan",
    ]
    if not report.exists() or any(section not in report_text for section in required_sections):
        print("Demo report was not generated correctly.")
        return 1
    if not fallback_report.exists() or "Manual Fallback Queries" not in fallback_report.read_text(encoding="utf-8-sig"):
        print("Fallback report was not generated correctly.")
        return 1
    if not fallback_csv.exists():
        print("Fallback CSV was not generated correctly.")
        return 1

    print("Package verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
