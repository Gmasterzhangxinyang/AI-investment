from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .context import AgentContext


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str
    when_to_use: str = ""
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()


class SkillRegistry:
    """Loads project Skills from skill folders.

    Each skill folder follows the SKILL.md + handler.py pattern. Metadata is
    discoverable; execution is deterministic Python.
    """

    def __init__(self, skills_dir: Path, package_prefix: str = "superpower.skills") -> None:
        self.skills_dir = skills_dir
        self.package_prefix = package_prefix
        self._metadata = self._discover_metadata()

    def list_skills(self) -> list[SkillMetadata]:
        return list(self._metadata.values())

    def metadata(self, name: str) -> SkillMetadata:
        if name not in self._metadata:
            raise KeyError(f"Unknown skill: {name}")
        return self._metadata[name]

    def run(self, name: str, context: AgentContext) -> dict[str, Any]:
        self.metadata(name)
        module_name = name.replace("-", "_")
        module = importlib.import_module(f"{self.package_prefix}.{module_name}.handler")
        skill_cls = getattr(module, "Skill")
        return skill_cls().run(context)

    def _discover_metadata(self) -> dict[str, SkillMetadata]:
        metadata: dict[str, SkillMetadata] = {}
        if not self.skills_dir.exists():
            return metadata

        for skill_dir in sorted(path for path in self.skills_dir.iterdir() if path.is_dir()):
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            parsed = _parse_skill_frontmatter(skill_md)
            name = str(parsed.get("name") or skill_dir.name)
            metadata[name] = SkillMetadata(
                name=name,
                description=str(parsed.get("description", "")),
                when_to_use=str(parsed.get("when_to_use", "")),
                inputs=tuple(parsed.get("inputs", [])),
                outputs=tuple(parsed.get("outputs", [])),
            )
        return metadata


def _parse_skill_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}

    end = text.find("\n---", 3)
    if end == -1:
        return {}

    body = text[3:end].strip().splitlines()
    parsed: dict[str, Any] = {}
    current_key: str | None = None

    for raw_line in body:
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key:
            parsed.setdefault(current_key, []).append(line[4:].strip())
            continue
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            current_key = key.strip()
            value = value.strip()
            parsed[current_key] = [] if value == "" else value
    return parsed

