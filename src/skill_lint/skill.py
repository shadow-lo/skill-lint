"""Load a SKILL.md file and split it into frontmatter and body."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

SKILL_FILENAME = "SKILL.md"


@dataclass
class Skill:
    path: Path
    """Path to the SKILL.md file."""
    text: str
    frontmatter: Optional[dict[str, Any]] = None
    """Parsed frontmatter, or None when it is missing or invalid."""
    frontmatter_error: Optional[str] = None
    body: str = ""
    body_start_line: int = 1
    """1-indexed line number where the body starts in the file."""
    raw_frontmatter: str = field(default="", repr=False)

    @property
    def folder(self) -> Path:
        return self.path.parent


def load_skill(path: Path) -> Skill:
    text = path.read_text(encoding="utf-8")
    skill = Skill(path=path, text=text)

    # Tolerate a UTF-8 BOM and Windows line endings.
    normalized = text.lstrip("﻿").replace("\r\n", "\n")
    lines = normalized.split("\n")

    if not lines or lines[0].strip() != "---":
        skill.frontmatter_error = "file does not start with a '---' frontmatter block"
        skill.body = normalized
        return skill

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        skill.frontmatter_error = "frontmatter block is never closed with '---'"
        skill.body = normalized
        return skill

    skill.raw_frontmatter = "\n".join(lines[1:end])
    skill.body = "\n".join(lines[end + 1 :])
    skill.body_start_line = end + 2

    try:
        data = yaml.safe_load(skill.raw_frontmatter)
    except yaml.YAMLError as exc:
        skill.frontmatter_error = f"frontmatter is not valid YAML: {exc}".splitlines()[0]
        return skill

    if data is None:
        data = {}
    if not isinstance(data, dict):
        skill.frontmatter_error = "frontmatter must be a YAML mapping (key: value pairs)"
        return skill

    skill.frontmatter = data
    return skill


def discover(paths: list[Path]) -> list[Path]:
    """Expand the given files/folders into a sorted list of SKILL.md files."""
    found: set[Path] = set()
    for p in paths:
        if p.is_file():
            found.add(p.resolve())
        elif p.is_dir():
            for candidate in p.rglob(SKILL_FILENAME):
                if any(part in {".git", "node_modules", ".venv"} for part in candidate.parts):
                    continue
                found.add(candidate.resolve())
    return sorted(found)
