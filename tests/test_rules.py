from pathlib import Path

import pytest

from skill_lint.rules import Config, lint
from skill_lint.skill import load_skill

from conftest import GOOD

GOOD_FILES = {"scripts/run.py": "print('hi')\n", "references/guide.md": "# Guide\n"}


def codes(path: Path, **kw) -> list[str]:
    return [f.code for f in lint(load_skill(path), **kw)]


def fm(name="my-skill", description="Turn meeting notes into action items. Use when the user pastes notes.", extra="", body="Do the thing.\n"):
    lines = ["---"]
    if name is not None:
        lines.append(f"name: {name}")
    if description is not None:
        lines.append(f"description: {description}")
    if extra:
        lines.append(extra)
    lines.append("---")
    return "\n".join(lines) + "\n\n" + body


def test_good_skill_is_clean(make_skill):
    assert codes(make_skill(GOOD, files=GOOD_FILES)) == []


def test_missing_frontmatter(make_skill):
    assert codes(make_skill("# Just a heading\n")) == ["SL001"]


def test_unclosed_frontmatter(make_skill):
    assert "SL001" in codes(make_skill("---\nname: my-skill\n"))


def test_invalid_yaml(make_skill):
    assert codes(make_skill("---\nname: [oops\n---\nbody\n")) == ["SL001"]


def test_missing_name_and_description(make_skill):
    assert set(codes(make_skill(fm(name=None, description=None)))) == {"SL002", "SL004"}


@pytest.mark.parametrize("name", ["My-Skill", "my_skill", "my--skill", "-skill", "a" * 65])
def test_bad_name_format(make_skill, name):
    folder = name if len(name) < 60 and "/" not in name else "my-skill"
    assert "SL003" in codes(make_skill(fm(name=name), folder=folder))


def test_reserved_words(make_skill):
    p = make_skill(fm(name="acme-helper"), folder="acme-helper")
    assert codes(p) == []
    assert codes(p, config=Config(reserved_words=("acme",))) == ["SL003"]


def test_name_folder_mismatch_is_warning(make_skill):
    assert codes(make_skill(fm(), folder="other")) == ["SL101"]


def test_description_too_long(make_skill):
    desc = "Use when " + "x" * 1100
    assert "SL005" in codes(make_skill(fm(description=desc)))


def test_description_angle_brackets(make_skill):
    assert "SL006" in codes(make_skill(fm(description="Use when the user wants <html> pages built for them.")))


def test_description_short_and_no_trigger(make_skill):
    assert codes(make_skill(fm(description="Does stuff"))) == ["SL102"]
    assert codes(make_skill(fm(description="Converts spreadsheets into neat charts and tables."))) == ["SL103"]


def test_multiline_description_is_supported(make_skill):
    content = "---\nname: my-skill\ndescription: >\n  Turn meeting notes into action items.\n  Use when the user pastes notes.\n---\n\nBody.\n"
    assert codes(make_skill(content)) == []


def test_unknown_key(make_skill):
    assert codes(make_skill(fm(extra="author: me"))) == ["SL104"]


def test_metadata_key_is_allowed(make_skill):
    assert codes(make_skill(fm(extra="metadata:\n  author: me"))) == []


def test_broken_references(make_skill):
    body = "Run `scripts/nope.sh`, see [guide](references/missing.md) and ![img](assets/x.png).\n"
    p = make_skill(fm(body=body))
    findings = lint(load_skill(p))
    assert [f.code for f in findings] == ["SL007", "SL007", "SL007"]
    assert all(f.line == 6 for f in findings)


def test_external_and_anchor_links_are_ignored(make_skill):
    body = "See [docs](https://example.com), [top](#top) and [mail](mailto:a@b.c).\n"
    assert codes(make_skill(fm(body=body))) == []


def test_links_in_code_fences_are_ignored(make_skill):
    body = "```\nRun scripts/nope.sh and [x](missing.md)\n`scripts/nope.sh`\n```\n"
    assert codes(make_skill(fm(body=body))) == []


def test_reference_outside_folder(make_skill, tmp_path):
    (tmp_path / "secret.md").write_text("x")
    assert codes(make_skill(fm(body="See [x](../secret.md).\n"))) == ["SL007"]


def test_link_with_anchor_resolves(make_skill):
    p = make_skill(fm(body="See [x](references/guide.md#setup).\n"), files=GOOD_FILES)
    assert codes(p) == []


def test_empty_body(make_skill):
    assert codes(make_skill(fm(body=""))) == ["SL008"]


def test_long_body(make_skill):
    assert codes(make_skill(fm(body="line\n" * 501))) == ["SL105"]


def test_ignore(make_skill):
    assert codes(make_skill(fm(), folder="other"), config=Config(ignore=frozenset({"SL101"}))) == []


def test_bom_and_crlf(make_skill):
    content = "﻿" + fm().replace("\n", "\r\n")
    assert codes(make_skill(content)) == []


def test_frontmatter_line_numbers(make_skill):
    p = make_skill(fm(name="Bad_Name"), folder="Bad_Name")
    (finding,) = lint(load_skill(p))
    assert finding.line == 2
