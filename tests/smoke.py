from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from superpower.runtime.skill_registry import SkillRegistry


def main() -> None:
    registry = SkillRegistry(ROOT / "backend" / "superpower" / "skills")
    names = {skill.name for skill in registry.list_skills()}
    required = {
        "wind-excel-ingestion",
        "data-quality-gate",
        "technical-indicators",
        "etf-rotation-strategy",
        "tl-timing-strategy",
        "convertible-bond-ranking",
        "strategy-backtest",
        "source-archive",
        "ai-research-committee",
        "report-generation",
    }
    missing = required - names
    if missing:
        raise SystemExit(f"Missing skills: {sorted(missing)}")
    print("smoke=ok")
    print(f"skills={len(names)}")


if __name__ == "__main__":
    main()
