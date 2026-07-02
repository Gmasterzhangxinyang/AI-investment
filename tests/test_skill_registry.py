from pathlib import Path

from superpower.runtime.skill_registry import SkillRegistry


def test_skill_registry_discovers_skills():
    root = Path(__file__).resolve().parents[1]
    registry = SkillRegistry(root / "backend" / "superpower" / "skills")
    names = {skill.name for skill in registry.list_skills()}
    assert "wind-excel-ingestion" in names
    assert "etf-rotation-strategy" in names
    assert "report-generation" in names

