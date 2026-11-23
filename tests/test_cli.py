import json

from skill_lint.cli import main

from conftest import GOOD

FILES = {"scripts/run.py": "", "references/guide.md": ""}


def test_clean_exit_zero(make_skill, capsys):
    p = make_skill(GOOD, files=FILES)
    assert main([str(p), "--no-color"]) == 0
    out = capsys.readouterr().out
    assert "1 skill(s) checked, 0 error(s), 0 warning(s)" in out


def test_errors_exit_one(make_skill):
    p = make_skill("no frontmatter\n")
    assert main([str(p)]) == 1


def test_warning_only_passes_unless_strict(make_skill):
    p = make_skill(GOOD, folder="other", files=FILES)
    assert main([str(p)]) == 0
    assert main([str(p), "--strict"]) == 1


def test_scans_folders_recursively(make_skill, tmp_path, capsys):
    make_skill(GOOD, folder="skills/my-skill", files=FILES)
    make_skill(GOOD.replace("my-skill", "two"), folder="skills/two", files=FILES)
    assert main([str(tmp_path), "--no-color"]) == 0
    assert "2 skill(s) checked" in capsys.readouterr().out


def test_json_output(make_skill, capsys):
    p = make_skill("no frontmatter\n")
    main([str(p), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert data[0]["findings"][0]["code"] == "SL001"
    assert data[0]["findings"][0]["severity"] == "error"


def test_github_output(make_skill, capsys):
    p = make_skill("no frontmatter\n")
    main([str(p), "--format", "github"])
    out = capsys.readouterr().out
    assert out.startswith("::error file=")
    assert "title=SL001" in out


def test_no_skills_found(tmp_path, capsys):
    assert main([str(tmp_path)]) == 2
    assert "no SKILL.md" in capsys.readouterr().err


def test_missing_path(tmp_path):
    assert main([str(tmp_path / "nope")]) == 2


def test_list_rules(capsys):
    assert main(["--list-rules"]) == 0
    out = capsys.readouterr().out
    assert "SL001" in out and "SL105" in out


def test_reserved_flag(make_skill):
    p = make_skill(GOOD.replace("my-skill", "acme-notes"), folder="acme-notes", files=FILES)
    assert main([str(p)]) == 0
    assert main([str(p), "--reserved", "Acme"]) == 1
