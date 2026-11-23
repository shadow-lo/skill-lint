from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest


@pytest.fixture
def make_skill(tmp_path: Path) -> Callable[..., Path]:
    def _make(content: str, folder: str = "my-skill", files: dict[str, str] | None = None) -> Path:
        d = tmp_path / folder
        d.mkdir(parents=True, exist_ok=True)
        for rel, text in (files or {}).items():
            f = d / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text, encoding="utf-8")
        p = d / "SKILL.md"
        p.write_text(content, encoding="utf-8")
        return p

    return _make


GOOD = """---
name: my-skill
description: Turn meeting notes into action items. Use when the user pastes meeting notes.
---

# My skill

Read `scripts/run.py` and the [guide](references/guide.md).
"""
