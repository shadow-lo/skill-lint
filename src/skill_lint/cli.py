"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .rules import RULES, Config, Finding, Severity, lint
from .skill import discover, load_skill


def _rel(path: Path) -> str:
    try:
        return os.path.relpath(path)
    except ValueError:  # different drive on Windows
        return str(path)


def format_text(results: dict[Path, list[Finding]], use_color: bool) -> str:
    red, yellow, green, dim, reset = ("\033[31m", "\033[33m", "\033[32m", "\033[2m", "\033[0m") if use_color else ("",) * 5
    out: list[str] = []
    errors = warnings = 0
    for path, findings in results.items():
        if not findings:
            out.append(f"{green}✓{reset} {_rel(path)}")
            continue
        out.append(f"{red if any(f.severity is Severity.ERROR for f in findings) else yellow}✗{reset} {_rel(path)}")
        for f in findings:
            color = red if f.severity is Severity.ERROR else yellow
            out.append(f"  {dim}{f.line:>4}{reset}  {color}{f.code}{reset}  {f.message}")
            if f.severity is Severity.ERROR:
                errors += 1
            else:
                warnings += 1
    out.append("")
    out.append(f"{len(results)} skill(s) checked, {errors} error(s), {warnings} warning(s)")
    return "\n".join(out)


def format_json(results: dict[Path, list[Finding]]) -> str:
    payload = [
        {
            "path": _rel(path),
            "findings": [
                {"code": f.code, "severity": f.severity.value, "line": f.line, "message": f.message}
                for f in findings
            ],
        }
        for path, findings in results.items()
    ]
    return json.dumps(payload, indent=2)


def format_github(results: dict[Path, list[Finding]]) -> str:
    lines = []
    for findings in results.values():
        for f in findings:
            level = "error" if f.severity is Severity.ERROR else "warning"
            msg = f.message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            lines.append(f"::{level} file={_rel(f.path)},line={f.line},title={f.code}::{msg}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="skill-lint",
        description="Lint Agent Skills (SKILL.md files) before you ship them.",
    )
    p.add_argument("paths", nargs="*", type=Path, default=[Path(".")], help="SKILL.md files or folders to scan (default: current folder)")
    p.add_argument("-f", "--format", choices=["text", "json", "github"], default="text", help="output format (default: text)")
    p.add_argument("--strict", action="store_true", help="exit non-zero on warnings too")
    p.add_argument("--ignore", default="", metavar="CODES", help="comma-separated rule codes to skip, e.g. SL101,SL103")
    p.add_argument("--reserved", default="", metavar="WORDS", help="comma-separated words a skill name must not contain, e.g. a brand name")
    p.add_argument("--no-color", action="store_true", help="disable colored output")
    p.add_argument("--list-rules", action="store_true", help="print every rule and exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_rules:
        for rule in RULES:
            print(f"{rule.code}  {rule.severity.value:<7}  {rule.summary}")
        return 0

    missing = [p for p in args.paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"skill-lint: {p}: no such file or folder", file=sys.stderr)
        return 2

    files = discover(args.paths)
    if not files:
        print("skill-lint: no SKILL.md files found", file=sys.stderr)
        return 2

    ignore = frozenset(c.strip().upper() for c in args.ignore.split(",") if c.strip())
    reserved = tuple(w.strip().lower() for w in args.reserved.split(",") if w.strip())
    config = Config(ignore=ignore, reserved_words=reserved)
    results = {path: lint(load_skill(path), config) for path in files}

    if args.format == "json":
        print(format_json(results))
    elif args.format == "github":
        text = format_github(results)
        if text:
            print(text)
        print(format_text(results, use_color=False), file=sys.stderr)
    else:
        use_color = not args.no_color and sys.stdout.isatty() and "NO_COLOR" not in os.environ
        print(format_text(results, use_color))

    all_findings = [f for fs in results.values() for f in fs]
    if any(f.severity is Severity.ERROR for f in all_findings):
        return 1
    if args.strict and all_findings:
        return 1
    return 0
