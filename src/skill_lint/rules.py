"""The lint rules. Each rule takes a Skill and yields Findings."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Iterator, Optional

from .skill import Skill

NAME_MAX = 64
DESCRIPTION_MAX = 1024
DESCRIPTION_MIN = 20
BODY_MAX_LINES = 500
KNOWN_KEYS = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TRIGGER_HINT_RE = re.compile(r"\b(use (this )?(skill )?(when|for|to)|when (the )?user|whenever|trigger)", re.I)
MD_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
CODE_PATH_RE = re.compile(r"`((?:\./)?(?:scripts|references|assets|templates|examples)/[^`\s]+)`")


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    message: str
    path: Path
    line: int = 1


@dataclass(frozen=True)
class Config:
    ignore: frozenset = frozenset()
    """Rule codes to skip."""
    reserved_words: tuple = ()
    """Words a skill name must not contain (for example a vendor or brand name)."""


@dataclass(frozen=True)
class Rule:
    code: str
    severity: Severity
    summary: str
    check: Callable[[Skill, "Rule", Config], Iterator[Finding]]

    def finding(self, skill: Skill, message: str, line: int = 1) -> Finding:
        return Finding(self.code, self.severity, message, skill.path, line)


def _line_of_key(skill: Skill, key: str) -> int:
    for i, line in enumerate(skill.raw_frontmatter.split("\n")):
        if line.startswith(f"{key}:"):
            return i + 2  # +1 for the opening '---', +1 for 1-indexing
    return 1


def _str_field(skill: Skill, key: str) -> Optional[str]:
    if not skill.frontmatter:
        return None
    value = skill.frontmatter.get(key)
    return value if isinstance(value, str) else None


# --- frontmatter -------------------------------------------------------------

def check_frontmatter(skill: Skill, rule: Rule, cfg: Config) -> Iterator[Finding]:
    if skill.frontmatter_error:
        yield rule.finding(skill, skill.frontmatter_error)


def check_name_present(skill: Skill, rule: Rule, cfg: Config) -> Iterator[Finding]:
    if skill.frontmatter is None:
        return
    value = skill.frontmatter.get("name")
    if value is None or (isinstance(value, str) and not value.strip()):
        yield rule.finding(skill, "frontmatter has no 'name'")
    elif not isinstance(value, str):
        yield rule.finding(skill, f"'name' must be a string, got {type(value).__name__}", _line_of_key(skill, "name"))


def check_name_format(skill: Skill, rule: Rule, cfg: Config) -> Iterator[Finding]:
    name = _str_field(skill, "name")
    if not name or not name.strip():
        return
    line = _line_of_key(skill, "name")
    if len(name) > NAME_MAX:
        yield rule.finding(skill, f"'name' is {len(name)} characters, the limit is {NAME_MAX}", line)
    if not NAME_RE.match(name):
        yield rule.finding(skill, f"'name' must be kebab-case (lowercase letters, digits and single hyphens): {name!r}", line)
    lowered = name.lower()
    for word in cfg.reserved_words:
        if word in lowered:
            yield rule.finding(skill, f"'name' must not contain the reserved word {word!r}", line)


def check_name_matches_folder(skill: Skill, rule: Rule, cfg: Config) -> Iterator[Finding]:
    name = _str_field(skill, "name")
    if not name:
        return
    folder = skill.folder.name
    if folder and name != folder:
        yield rule.finding(skill, f"'name' is {name!r} but the folder is {folder!r}", _line_of_key(skill, "name"))


def check_description_present(skill: Skill, rule: Rule, cfg: Config) -> Iterator[Finding]:
    if skill.frontmatter is None:
        return
    value = skill.frontmatter.get("description")
    if value is None or (isinstance(value, str) and not value.strip()):
        yield rule.finding(skill, "frontmatter has no 'description'; the agent uses it to decide when to load the skill")
    elif not isinstance(value, str):
        yield rule.finding(skill, f"'description' must be a string, got {type(value).__name__}", _line_of_key(skill, "description"))


def check_description_length(skill: Skill, rule: Rule, cfg: Config) -> Iterator[Finding]:
    desc = _str_field(skill, "description")
    if not desc or not desc.strip():
        return
    if len(desc) > DESCRIPTION_MAX:
        yield rule.finding(skill, f"'description' is {len(desc)} characters, the limit is {DESCRIPTION_MAX}", _line_of_key(skill, "description"))


def check_description_too_short(skill: Skill, rule: Rule, cfg: Config) -> Iterator[Finding]:
    desc = _str_field(skill, "description")
    if desc and desc.strip() and len(desc.strip()) < DESCRIPTION_MIN:
        yield rule.finding(skill, f"'description' is only {len(desc.strip())} characters; say what the skill does and when to use it", _line_of_key(skill, "description"))


def check_description_brackets(skill: Skill, rule: Rule, cfg: Config) -> Iterator[Finding]:
    desc = _str_field(skill, "description")
    if desc and ("<" in desc or ">" in desc):
        yield rule.finding(skill, "'description' must not contain angle brackets (< or >)", _line_of_key(skill, "description"))


def check_description_trigger(skill: Skill, rule: Rule, cfg: Config) -> Iterator[Finding]:
    desc = _str_field(skill, "description")
    if desc and len(desc.strip()) >= DESCRIPTION_MIN and not TRIGGER_HINT_RE.search(desc):
        yield rule.finding(skill, "'description' does not say when to use the skill (e.g. \"Use when ...\")", _line_of_key(skill, "description"))


def check_unknown_keys(skill: Skill, rule: Rule, cfg: Config) -> Iterator[Finding]:
    if not skill.frontmatter:
        return
    for key in skill.frontmatter:
        if key not in KNOWN_KEYS:
            yield rule.finding(skill, f"unknown frontmatter key {key!r}; put custom fields under 'metadata'", _line_of_key(skill, str(key)))


# --- body ---------------------------------------------------------------------

def _is_local(target: str) -> bool:
    return not (
        target.startswith(("http://", "https://", "mailto:", "#", "/"))
        or "://" in target
    )


def _references(skill: Skill) -> Iterator[tuple[str, int]]:
    in_fence = False
    for offset, line in enumerate(skill.body.split("\n")):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        lineno = skill.body_start_line + offset
        for regex in (MD_LINK_RE, MD_IMAGE_RE, CODE_PATH_RE):
            for m in regex.finditer(line):
                yield m.group(1), lineno


def check_broken_references(skill: Skill, rule: Rule, cfg: Config) -> Iterator[Finding]:
    seen: set[tuple[str, int]] = set()
    for target, lineno in _references(skill):
        if (target, lineno) in seen or not _is_local(target):
            continue
        seen.add((target, lineno))
        clean = target.split("#", 1)[0].split("?", 1)[0]
        if not clean:
            continue
        resolved = (skill.folder / clean).resolve()
        if not resolved.exists():
            yield rule.finding(skill, f"references {target!r}, which does not exist", lineno)
        elif skill.folder.resolve() not in resolved.parents and resolved != skill.folder.resolve():
            yield rule.finding(skill, f"references {target!r}, which is outside the skill folder", lineno)


def check_body_empty(skill: Skill, rule: Rule, cfg: Config) -> Iterator[Finding]:
    if skill.frontmatter is not None and not skill.body.strip():
        yield rule.finding(skill, "SKILL.md has no instructions after the frontmatter", skill.body_start_line)


def check_body_length(skill: Skill, rule: Rule, cfg: Config) -> Iterator[Finding]:
    n = len(skill.body.rstrip("\n").split("\n"))
    if n > BODY_MAX_LINES:
        yield rule.finding(skill, f"body is {n} lines; keep SKILL.md under {BODY_MAX_LINES} and move detail into referenced files", skill.body_start_line)


RULES: list[Rule] = [
    Rule("SL001", Severity.ERROR, "SKILL.md has a valid YAML frontmatter block", check_frontmatter),
    Rule("SL002", Severity.ERROR, "frontmatter has a 'name'", check_name_present),
    Rule("SL003", Severity.ERROR, "'name' is kebab-case, at most 64 chars, no reserved words (--reserved)", check_name_format),
    Rule("SL004", Severity.ERROR, "frontmatter has a 'description'", check_description_present),
    Rule("SL005", Severity.ERROR, "'description' is at most 1024 characters", check_description_length),
    Rule("SL006", Severity.ERROR, "'description' has no angle brackets", check_description_brackets),
    Rule("SL007", Severity.ERROR, "local links and script paths in the body exist inside the skill folder", check_broken_references),
    Rule("SL008", Severity.ERROR, "the body is not empty", check_body_empty),
    Rule("SL101", Severity.WARNING, "'name' matches the folder name", check_name_matches_folder),
    Rule("SL102", Severity.WARNING, "'description' is not too short", check_description_too_short),
    Rule("SL103", Severity.WARNING, "'description' says when to use the skill", check_description_trigger),
    Rule("SL104", Severity.WARNING, "no unknown frontmatter keys", check_unknown_keys),
    Rule("SL105", Severity.WARNING, f"the body is under {BODY_MAX_LINES} lines", check_body_length),
]


def lint(skill: Skill, config: Optional[Config] = None) -> list[Finding]:
    cfg = config or Config()
    findings: list[Finding] = []
    for rule in RULES:
        if rule.code in cfg.ignore:
            continue
        findings.extend(rule.check(skill, rule, cfg))
    return sorted(findings, key=lambda f: (f.line, f.code))
