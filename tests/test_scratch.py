"""tools/scratch.py: deletion is refused unless the target is provably inside a workspace it made.

Safety rule for these tests: a system path (/dev/null, /, the home directory...) is only ever given
to the pure validator `assert_removable`, which cannot delete. Nothing that can delete is pointed
at a path outside a pytest temporary directory.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import scratch
from scratch import RefusedRemovalError, assert_removable, new_workspace, remove, remove_workspace


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    return new_workspace("test-ws-", base=tmp_path)


def populate(root: Path, relative: str, text: str = "x") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


# ------------------------------------------------------------- the workspace


def test_a_new_workspace_is_marked_unique_and_inside_the_temporary_directory(ws: Path) -> None:
    assert (ws / scratch.MARKER).is_file()
    assert any(ws.is_relative_to(base) for base in scratch.allowed_bases())
    assert new_workspace("test-ws-", base=ws.parent) != ws


def test_a_directory_without_the_marker_is_not_a_workspace(tmp_path: Path) -> None:
    unmarked = tmp_path / "unmarked"
    populate(unmarked, "child/file.txt")
    with pytest.raises(RefusedRemovalError, match="not a workspace"):
        assert_removable(unmarked / "child", unmarked)
    with pytest.raises(RefusedRemovalError, match="not a workspace"):
        remove_workspace(unmarked)
    assert (unmarked / "child/file.txt").exists()


def test_a_marker_that_is_a_symlink_does_not_count(tmp_path: Path) -> None:
    fake = tmp_path / "fake"
    fake.mkdir()
    real = populate(tmp_path, "elsewhere/marker")
    (fake / scratch.MARKER).symlink_to(real)
    with pytest.raises(RefusedRemovalError, match="not a workspace"):
        remove_workspace(fake)


def test_a_workspace_that_is_a_symlink_is_refused(ws: Path, tmp_path: Path) -> None:
    link = tmp_path / "link-to-ws"
    link.symlink_to(ws, target_is_directory=True)
    with pytest.raises(RefusedRemovalError, match="symbolic link"):
        remove_workspace(link)
    assert ws.exists()


def test_a_marked_directory_outside_the_temporary_directories_is_refused(
    ws: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    populate(ws, "child/file.txt")
    monkeypatch.setattr(scratch, "allowed_bases", lambda: [tmp_path / "somewhere-else"])
    with pytest.raises(RefusedRemovalError, match="not under the system temporary directory"):
        assert_removable(ws / "child", ws)
    with pytest.raises(RefusedRemovalError, match="not under the system temporary directory"):
        remove_workspace(ws)
    assert (ws / "child/file.txt").exists()


@pytest.mark.parametrize("which", ["home", "cwd"])
def test_a_workspace_that_is_or_contains_home_or_the_cwd_is_refused(
    ws: Path, monkeypatch: pytest.MonkeyPatch, which: str
) -> None:
    populate(ws, "child/file.txt")
    if which == "home":
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: ws))
    else:
        monkeypatch.chdir(ws / "child")
    with pytest.raises(RefusedRemovalError, match="home directory|current directory"):
        remove_workspace(ws)
    assert (ws / "child/file.txt").exists()


# ------------------------------------------------------------- validation only: system paths


@pytest.mark.parametrize("target", ["/dev/null", "/", "/etc", "/usr", "/tmp", "/private/tmp", "/var"])
def test_system_paths_are_refused_by_the_validator(ws: Path, target: str) -> None:
    """Validation only. The validator cannot delete, so this is safe to run against real system paths."""
    before = Path(target).exists()
    with pytest.raises(RefusedRemovalError):
        assert_removable(Path(target), ws)
    assert Path(target).exists() == before


def test_the_home_directory_and_its_parents_are_refused_by_the_validator(ws: Path) -> None:
    for target in (Path.home(), Path.home().parent, Path.cwd()):
        with pytest.raises(RefusedRemovalError):
            assert_removable(target, ws)


# ------------------------------------------------------------- targets


def test_a_target_outside_the_workspace_is_refused_and_untouched(ws: Path, tmp_path: Path) -> None:
    outside = populate(tmp_path, "sibling/precious.txt")
    with pytest.raises(RefusedRemovalError, match="outside the workspace"):
        remove(outside.parent, ws)
    assert outside.read_text() == "x"


def test_dot_dot_traversal_out_of_the_workspace_is_refused(ws: Path, tmp_path: Path) -> None:
    outside = populate(tmp_path, "sibling/precious.txt")
    with pytest.raises(RefusedRemovalError, match="outside the workspace"):
        remove(ws / ".." / "sibling", ws)
    assert outside.exists()


def test_the_workspace_itself_and_its_marker_cannot_be_removed_as_a_child(ws: Path) -> None:
    for target in (ws, ws / scratch.MARKER):
        with pytest.raises(RefusedRemovalError):
            assert_removable(target, ws)
    assert (ws / scratch.MARKER).exists()


def test_symbolic_links_are_never_followed_or_removed(ws: Path, tmp_path: Path) -> None:
    outside = populate(tmp_path, "sibling/precious.txt")
    inside = populate(ws, "real/file.txt")
    (ws / "link-out").symlink_to(outside.parent, target_is_directory=True)
    (ws / "link-in").symlink_to(inside.parent, target_is_directory=True)
    for name in ("link-out", "link-in"):
        with pytest.raises(RefusedRemovalError, match="symbolic link"):
            remove(ws / name, ws)
    assert outside.exists() and inside.exists()


def test_a_path_through_a_symlink_that_escapes_is_refused(ws: Path, tmp_path: Path) -> None:
    outside = populate(tmp_path, "sibling/deep/precious.txt")
    (ws / "gate").symlink_to(outside.parent.parent, target_is_directory=True)
    with pytest.raises(RefusedRemovalError, match="outside the workspace"):
        remove(ws / "gate" / "deep", ws)
    assert outside.exists()


def test_missing_targets_and_special_files_are_refused(ws: Path) -> None:
    with pytest.raises(RefusedRemovalError, match="does not exist"):
        remove(ws / "nope", ws)
    os.mkfifo(ws / "pipe")
    with pytest.raises(RefusedRemovalError, match="regular file or directory"):
        remove(ws / "pipe", ws)
    assert (ws / "pipe").exists()


# ------------------------------------------------------------- the deletions that are allowed


def test_a_child_directory_and_a_file_can_be_removed_and_nothing_else(ws: Path) -> None:
    keep = populate(ws, "keep/file.txt")
    populate(ws, "drop/nested/file.txt")
    single = populate(ws, "single.txt")
    remove(ws / "drop", ws)
    remove(single, ws)
    assert not (ws / "drop").exists() and not single.exists()
    assert keep.exists() and (ws / scratch.MARKER).exists() and ws.exists()


def test_a_whole_workspace_can_be_removed(ws: Path) -> None:
    populate(ws, "a/b/c.txt")
    remove_workspace(ws)
    assert not ws.exists()


# ------------------------------------------------------------- the command line (temporary targets only)


def test_cli_creates_and_removes_a_workspace(capsys: pytest.CaptureFixture[str]) -> None:
    assert scratch.main(["new", "--prefix", "scratch-cli-test-"]) == 0
    path = Path(capsys.readouterr().out.strip())
    assert (path / scratch.MARKER).is_file()
    assert scratch.main(["clean", str(path)]) == 0
    assert not path.exists()


def test_cli_validates_every_child_before_removing_any(
    ws: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    valid = populate(ws, "valid/file.txt")
    outside = populate(tmp_path, "outside/file.txt")
    code = scratch.main(["clean", str(ws), str(valid.parent), str(outside.parent)])
    assert code == 2
    assert "outside the workspace" in capsys.readouterr().err
    assert valid.exists() and outside.exists()  # the valid one was not removed either


def test_cli_refuses_an_unmarked_temporary_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    unmarked = tmp_path / "unmarked"
    populate(unmarked, "file.txt")
    assert scratch.main(["clean", str(unmarked)]) == 2
    assert "not a workspace" in capsys.readouterr().err
    assert (unmarked / "file.txt").exists()
