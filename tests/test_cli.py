from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from conftest import make_template_repo
from devkit import cli


@pytest.fixture()
def template(tmp_path: Path) -> str:
    return str(make_template_repo(tmp_path / "tpl", ("v0.1.0",)))


@pytest.fixture()
def out(tmp_path: Path) -> Path:
    directory = tmp_path / "out"
    directory.mkdir()
    return directory


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    assert "devkit" in capsys.readouterr().out


def test_a_command_is_required() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main([])
    assert exit_info.value.code == 2


def test_new_dry_run_succeeds_and_writes_nothing(
    template: str, out: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(["new", "cli-app", "--dry-run", "--template", template, "--output-dir", str(out)])
    captured = capsys.readouterr()
    assert code == 0
    assert "Dry run complete. Nothing was written." in captured.out
    assert "[dry run] Profile 'web-core', local template" in captured.out
    assert list(out.iterdir()) == []


def test_new_creates_the_app_and_passes_options(
    template: str, out: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(
        ["new", "cli-app", "--description", "Made by the CLI", "--set", "cache_components=false",
         "--template", template, "--output-dir", str(out)]
    )  # fmt: skip
    assert code == 0
    project = out / "cli-app"
    assert "Made by the CLI" in (project / "README.md").read_text()
    assert (project / "flags.txt").read_text().strip() == "cache_components=false"
    assert "npm run check" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["new", "Bad"], "Validation error for question 'app_name'"),
        (["new", "../escape"], "Invalid name"),
        (["new", "fine", "--set", "nonsense=1"], "Unknown option"),
        (["new", "fine", "--set", "cache_components=maybe"], "true/false"),
        (["new", "fine", "--profile", "full-stack"], "reserved for a later milestone"),
        (["new", "fine", "--profile", "native-ios"], "reserved for a later milestone"),
    ],
)
def test_rejected_input_exits_2_and_writes_nothing(
    argv: list[str], message: str, template: str, out: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main([*argv, "--template", template, "--output-dir", str(out)])
    assert code == 2
    assert message in capsys.readouterr().err
    assert list(out.iterdir()) == []


def test_existing_destination_exits_1_and_preserves_it(
    template: str, out: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (out / "taken").mkdir()
    (out / "taken" / "keep.txt").write_text("keep")
    code = cli.main(["new", "taken", "--template", template, "--output-dir", str(out)])
    assert code == 1
    assert "already exists" in capsys.readouterr().err
    assert [p.name for p in (out / "taken").iterdir()] == ["keep.txt"]


def test_unavailable_template_exits_1_without_leaking_credentials(
    out: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    url = "https://someone:hunter2-token@localhost:9/none.git"
    code = cli.main(["new", "app", "--template", url, "--output-dir", str(out)])
    err = capsys.readouterr().err
    assert code == 1
    assert "unavailable" in err and "hunter2-token" not in err
    assert list(out.iterdir()) == []


def test_the_default_published_template_being_unavailable_suggests_a_local_checkout(
    tmp_path: Path, out: Path, point_profile_at, capsys: pytest.CaptureFixture[str]
) -> None:
    point_profile_at(str(tmp_path / "not-published-yet.git"))
    code = cli.main(["new", "app", "--output-dir", str(out)])
    assert code == 1
    assert "--template" in capsys.readouterr().err
    assert list(out.iterdir()) == []


def test_a_release_outside_the_supported_range_exits_2(
    tmp_path: Path, out: Path, point_profile_at, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_template_repo(tmp_path / "tpl", ("v0.1.0", "v0.2.0"))
    point_profile_at(str(repo))
    code = cli.main(["new", "app", "--template-ref", "v0.2.0", "--output-dir", str(out)])
    assert code == 2
    assert "outside the range" in capsys.readouterr().err
    assert list(out.iterdir()) == []


def test_doctor_exits_nonzero_when_required_tools_are_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert cli.main(["doctor"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_module_entry_point_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "devkit", "--help"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert "doctor" in result.stdout and "new" in result.stdout
