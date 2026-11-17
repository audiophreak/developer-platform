"""`devkit upgrade`: small, strict, and never destructive.

The versioned mini template mirrors the real release history (v0.1.x has no `zod`, v0.2.x has it)
and is served at an https-style origin, so the project records a real-looking portable URL.
After every refusal the project must be exactly as it was.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import make_remote, make_versioned_template, publish, release, run_git
from devkit import cli
from devkit.errors import OperationError, TemplateUnavailableError, UpgradeConflictError, UsageError
from devkit.generate import NewRequest, generate_project
from devkit.upgrade import UpgradeRequest, read_answers, upgrade_project


@pytest.fixture()
def world(tmp_path, point_profile_at, https_origin):
    """(repo, remote, out): releases v0.1.0, v0.1.1, v0.2.0, v0.2.1 published; devkit supports 0.1-0.2."""
    repo = make_versioned_template(tmp_path / "work" / "web-core-template")
    remote = make_remote(repo, tmp_path / "remote" / "web-core-template.git")
    point_profile_at(https_origin(remote), versions=((0, 1, 0), (0, 3, 0)))
    out = tmp_path / "out"
    out.mkdir()
    return repo, remote, out


def project_at(out: Path, tag: str, *options: str, name: str = "app") -> Path:
    """A generated project at `tag`, adopted into git with the user's own work committed."""
    project = generate_project(NewRequest(name, output_dir=out, template_ref=tag, options=options)).destination
    run_git(project, "init", "-q", "-b", "main")
    (project / "notes.txt").write_text("my own file\n")
    readme = project / "README.md"
    readme.write_text(readme.read_text() + "\nLocal note.\n")
    run_git(project, "add", "-A")
    run_git(project, "commit", "-q", "-m", "initial")
    return project


def answers(project: Path) -> dict[str, str]:
    return read_answers((project / ".copier-answers.yml").read_text())


def snapshot(project: Path) -> dict[str, bytes]:
    return {str(p.relative_to(project)): p.read_bytes() for p in sorted(project.rglob("*")) if p.is_file() and ".git" not in p.parts}


def head(project: Path) -> str:
    return run_git(project, "rev-parse", "HEAD").strip()


def assert_untouched(project: Path, before: dict[str, bytes], commit: str) -> None:
    assert snapshot(project) == before and head(project) == commit


def upgrade(project: Path, **kwargs):
    return upgrade_project(UpgradeRequest(project=project, **kwargs))


# ------------------------------------------------------------------ the happy path


def test_upgrades_to_the_newest_supported_release_keeping_selections_and_user_work(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.1.0", "cache_components=false")
    commit = head(project)

    result = upgrade(project)

    assert result.changed and result.plan.target == (0, 2, 1)
    recorded = answers(project)
    assert recorded["_commit"] == "v0.2.1"
    assert recorded["cache_components"] == "false"  # the selection was kept
    assert recorded["zod"] == "false"  # a feature the new release introduces stays off
    assert (project / "version.txt").read_text().strip() == "0.2.1"
    assert (project / "notes.txt").read_text() == "my own file\n"
    assert "Local note." in (project / "README.md").read_text()
    assert head(project) == commit  # nothing was committed for the user
    assert "M" in run_git(project, "status", "--porcelain")  # the changes are there to review


def test_a_selected_feature_survives_the_upgrade(world) -> None:
    repo, remote, out = world
    project = project_at(out, "v0.2.0", "zod=true")
    release(repo, "v0.2.2")
    publish(repo, remote, "v0.2.2")

    upgrade(project)

    assert answers(project)["_commit"] == "v0.2.2" and answers(project)["zod"] == "true"
    assert (project / "flags.txt").read_text().splitlines() == ["cache_components=true", "zod=true"]


def test_an_option_can_be_changed_during_the_upgrade(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.1.0")
    result = upgrade(project, options=("zod=true",))
    assert result.plan.options == {"zod": True}
    assert answers(project)["zod"] == "true"
    assert (project / "flags.txt").read_text().splitlines() == ["cache_components=true", "zod=true"]


def test_to_picks_a_specific_supported_release(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.1.0")
    result = upgrade(project, to="v0.2.0")
    assert result.plan.target == (0, 2, 0) and answers(project)["_commit"] == "v0.2.0"


def test_a_project_from_a_local_development_origin_can_upgrade_with_a_warning(world, tmp_path) -> None:
    repo, _, out = world
    project = generate_project(
        NewRequest("dev-app", output_dir=out, template=str(repo), template_ref="v0.1.0")
    ).destination
    run_git(project, "init", "-q", "-b", "main")
    run_git(project, "add", "-A")
    run_git(project, "commit", "-q", "-m", "initial")
    result = upgrade(project)
    assert result.changed and answers(project)["_commit"] == "v0.2.1"
    assert any("development origin" in note for note in result.plan.warnings)


# ------------------------------------------------------------------ nothing to do, and previews


def test_already_up_to_date_changes_nothing(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.2.1")
    before, commit = snapshot(project), head(project)
    result = upgrade(project)
    assert not result.changed and result.plan.target is None
    assert_untouched(project, before, commit)


def test_dry_run_shows_the_plan_and_changes_nothing(world, capsys) -> None:
    _, _, out = world
    project = project_at(out, "v0.1.0", "cache_components=false")
    before, commit = snapshot(project), head(project)

    code = cli.main(["upgrade", str(project), "--dry-run", "--set", "zod=true"])
    text = capsys.readouterr().out

    assert code == 0
    assert "[dry run] Upgrading v0.1.0 -> v0.2.1" in text
    assert "Keeping your answers:" in text and "cache_components=false" in text
    assert "Changing: zod=true" in text and "Nothing was changed" in text
    assert "crosses a minor version" in text
    assert_untouched(project, before, commit)
    assert run_git(project, "status", "--porcelain") == ""


# ------------------------------------------------------------------ refusals leave everything as it was


def test_refuses_a_project_with_modified_files(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.1.0")
    (project / "notes.txt").write_text("edited but not committed\n")
    before, commit = snapshot(project), head(project)
    with pytest.raises(OperationError, match="uncommitted changes"):
        upgrade(project)
    assert_untouched(project, before, commit)


def test_refuses_a_project_with_untracked_files(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.1.0")
    (project / "scratch.txt").write_text("new, not added\n")
    before, commit = snapshot(project), head(project)
    with pytest.raises(OperationError, match="uncommitted changes"):
        upgrade(project)
    assert_untouched(project, before, commit)


def test_refuses_a_project_that_is_not_a_git_repository_root(world) -> None:
    _, _, out = world
    project = generate_project(NewRequest("plain", output_dir=out, template_ref="v0.1.0")).destination
    before = snapshot(project)
    with pytest.raises(OperationError, match="not the root of a git repository"):
        upgrade(project)
    assert snapshot(project) == before
    # a subdirectory of another repository is not a root either
    run_git(out, "init", "-q", "-b", "main")
    with pytest.raises(OperationError, match="not the root of a git repository"):
        upgrade(project)
    assert snapshot(project) == before


def test_refuses_a_directory_that_is_not_a_template_project(world, tmp_path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(OperationError, match="was not generated from a Copier template"):
        upgrade(empty)
    with pytest.raises(OperationError, match="does not exist"):
        upgrade(tmp_path / "nowhere")


@pytest.mark.parametrize(
    ("recorded", "message"),
    [("v0.1.0-3-gabc1234", "unreleased template"), ("abc1234", "not a release tag"), ("0.1.0", "not a release tag")],
)
def test_refuses_a_project_whose_recorded_version_is_not_a_release(world, recorded: str, message: str) -> None:
    _, _, out = world
    project = project_at(out, "v0.1.0")
    path = project / ".copier-answers.yml"
    path.write_text(path.read_text().replace("_commit: v0.1.0", f"_commit: {recorded}"))
    run_git(project, "commit", "-q", "-am", "tamper")
    before, commit = snapshot(project), head(project)
    with pytest.raises(OperationError, match=message):
        upgrade(project)
    assert_untouched(project, before, commit)


def test_refuses_a_project_outside_the_supported_range(world, point_profile_at) -> None:
    _, _, out = world
    older = project_at(out, "v0.1.0", name="older")
    newer = project_at(out, "v0.2.0", name="newer")
    origin = answers(older)["_src_path"]
    snapshots = {p: (snapshot(p), head(p)) for p in (older, newer)}

    point_profile_at(origin, versions=((0, 2, 0), (0, 3, 0)))  # a devkit that no longer supports 0.1.x
    with pytest.raises(UsageError, match="older than the oldest release this devkit supports"):
        upgrade(older)

    point_profile_at(origin, versions=((0, 1, 0), (0, 2, 0)))  # a devkit that predates 0.2.x
    with pytest.raises(UsageError, match="newer than this devkit supports"):
        upgrade(newer)

    for project, (before, commit) in snapshots.items():
        assert_untouched(project, before, commit)


@pytest.mark.parametrize(
    ("to", "error", "message"),
    [
        ("v0.3.0", UsageError, "outside the range"),
        ("v0.2.9", OperationError, "does not exist"),
        ("latest", UsageError, "not a release tag"),
        ("v0.1.0", UsageError, "Refusing to downgrade"),
    ],
)
def test_refuses_unsupported_targets(world, to: str, error: type[Exception], message: str) -> None:
    _, _, out = world
    project = project_at(out, "v0.2.0")
    before, commit = snapshot(project), head(project)
    with pytest.raises(error, match=message):
        upgrade(project, to=to)
    assert_untouched(project, before, commit)


def test_refuses_an_option_the_target_release_lacks(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.1.0")
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError, match="'zod' needs template v0.2.0 or newer, but release v0.1.1"):
        upgrade(project, to="v0.1.1", options=("zod=true",))
    assert_untouched(project, before, commit)


@pytest.mark.parametrize("option", ["zod=banana", "zod", "nonexistent=true", "app_name=x"])
def test_refuses_bad_options_before_touching_anything(world, option: str) -> None:
    _, _, out = world
    project = project_at(out, "v0.1.0")
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError):
        upgrade(project, options=(option,))
    assert_untouched(project, before, commit)


def test_refuses_an_unavailable_template_source(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.1.0")
    path = project / ".copier-answers.yml"
    path.write_text(path.read_text().replace(answers(project)["_src_path"], str(out / "never-existed.git")))
    run_git(project, "commit", "-q", "-am", "point at a missing origin")
    before, commit = snapshot(project), head(project)
    with pytest.raises(TemplateUnavailableError, match="unavailable"):
        upgrade(project)
    assert_untouched(project, before, commit)


def test_a_reserved_profile_is_a_usage_error(world, capsys) -> None:
    _, _, out = world
    project = project_at(out, "v0.1.0")
    assert cli.main(["upgrade", str(project), "--profile", "native-ios"]) == 2
    assert "reserved for a later milestone" in capsys.readouterr().err


# ------------------------------------------------------------------ conflicts: reported, never discarded


def test_conflicting_edits_are_reported_and_both_sides_are_kept(world, capsys) -> None:
    _, _, out = world
    project = project_at(out, "v0.1.0")
    (project / "version.txt").write_text("my own version note\n")  # the template changes this same line
    run_git(project, "commit", "-q", "-am", "edit a template-owned file")
    commit = head(project)

    code = cli.main(["upgrade", str(project)])
    err = capsys.readouterr().err

    assert code == 3
    assert "merge conflicts in: version.txt" in err and "Nothing was discarded" in err
    merged = (project / "version.txt").read_text()
    assert "<<<<<<<" in merged and ">>>>>>>" in merged
    assert "my own version note" in merged and "0.2.1" in merged  # neither side was lost
    assert (project / "notes.txt").read_text() == "my own file\n"
    assert head(project) == commit
    assert answers(project)["_commit"] == "v0.2.1"  # the rest of the upgrade completed


def test_the_conflict_exit_code_is_distinct() -> None:
    assert UpgradeConflictError.exit_code == 3 and UsageError.exit_code == 2 and OperationError.exit_code == 1


# ------------------------------------------------------------------ command-line behaviour


def test_success_prints_the_next_steps(world, capsys) -> None:
    _, _, out = world
    project = project_at(out, "v0.1.0")
    assert cli.main(["upgrade", str(project)]) == 0
    text = capsys.readouterr().out
    assert "Upgraded to v0.2.1" in text and "npm ci" in text and "npm run check" in text and "git diff" in text


def test_an_unsupported_project_exits_with_the_documented_codes(world, capsys) -> None:
    _, _, out = world
    project = project_at(out, "v0.1.0")
    (project / "scratch.txt").write_text("x")
    assert cli.main(["upgrade", str(project)]) == 1  # dirty: an operation failure
    assert cli.main(["upgrade", str(project), "--to", "v9.0.0"]) == 2  # unsupported: a usage error
    capsys.readouterr()


def test_read_answers_handles_quotes_and_ignores_other_lines() -> None:
    text = "# comment\n_commit: v0.1.0\n_src_path: 'https://x.invalid/t.git'\napp_description: \"A b\"\nzod: true\n  nested: no\n"
    assert read_answers(text) == {"_commit": "v0.1.0", "_src_path": "https://x.invalid/t.git", "app_description": "A b", "zod": "true"}


def test_a_feature_can_be_switched_on_at_the_release_the_project_already_has(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.2.1")
    assert answers(project)["zod"] == "false"
    commit = head(project)

    result = upgrade(project, options=("zod=true",))

    assert result.changed and result.plan.target == (0, 2, 1)
    assert answers(project)["zod"] == "true" and answers(project)["_commit"] == "v0.2.1"
    assert (project / "flags.txt").read_text().splitlines() == ["cache_components=true", "zod=true"]
    assert (project / "notes.txt").read_text() == "my own file\n"
    assert head(project) == commit
