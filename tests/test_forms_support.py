"""devkit 0.4 supports template releases 0.1.x to 0.3.x and offers the `forms` option from 0.3.0.

The versioned mini template mirrors the real release history: v0.1.x has no `zod`, v0.2.x has it,
v0.3.x adds `forms`, whose prerequisite (`zod`) is enforced by the template's own validator. devkit
must not duplicate that rule: it only knows which release first has the option. After every refusal
nothing may have been created or changed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import make_remote, make_versioned_template, publish, release, run_git
from devkit import cli
from devkit.errors import OperationError, UsageError
from devkit.generate import NewRequest, generate_project
from devkit.profiles import PROFILES
from devkit.upgrade import UpgradeRequest, read_answers, upgrade_project
from devkit.validation import ensure_options_available, parse_options
from devkit.sources import ResolvedTemplate

SPEC = PROFILES["web-core"].template
OPTION = next(o for o in SPEC.options if o.name == "forms")


@pytest.fixture()
def world(tmp_path, point_profile_at, https_origin):
    """(repo, remote, out): v0.1.0 to v0.3.1 published; the registry supports >=0.1.0,<0.4.0."""
    repo = make_versioned_template(tmp_path / "work" / "web-core-template", through_forms=True)
    remote = make_remote(repo, tmp_path / "remote" / "web-core-template.git")
    point_profile_at(https_origin(remote), versions=((0, 1, 0), (0, 4, 0)))
    out = tmp_path / "out"
    out.mkdir()
    return repo, remote, out


def entries(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


def answers(project: Path) -> dict:
    return yaml.safe_load((project / ".copier-answers.yml").read_text())


def flags(project: Path) -> list[str]:
    return (project / "flags.txt").read_text().splitlines()


def project_at(out: Path, tag: str, *options: str, name: str = "app") -> Path:
    """A generated project, adopted into git with the user's own work committed."""
    project = generate_project(NewRequest(name, output_dir=out, template_ref=tag, options=options)).destination
    run_git(project, "init", "-q", "-b", "main")
    (project / "notes.txt").write_text("my own file\n")
    readme = project / "README.md"
    readme.write_text(readme.read_text() + "\nLocal note.\n")
    run_git(project, "add", "-A")
    run_git(project, "commit", "-q", "-m", "initial")
    return project


def snapshot(project: Path) -> dict[str, bytes]:
    return {str(p.relative_to(project)): p.read_bytes() for p in sorted(project.rglob("*")) if p.is_file() and ".git" not in p.parts}


def head(project: Path) -> str:
    return run_git(project, "rev-parse", "HEAD").strip()


def upgrade(project: Path, **kwargs):
    return upgrade_project(UpgradeRequest(project=project, **kwargs))


def assert_untouched(project: Path, before: dict[str, bytes], commit: str) -> None:
    assert snapshot(project) == before and head(project) == commit


# ------------------------------------------------------------------ the registry


def test_forms_is_a_boolean_option_that_defaults_off_and_starts_at_template_0_3_0() -> None:
    assert (OPTION.kind, OPTION.default, OPTION.since) == ("bool", False, (0, 3, 0))
    assert "zod" in OPTION.help  # the prerequisite is described to the user...
    assert not hasattr(OPTION, "requires")  # ...but never encoded as a rule in devkit


def test_the_prerequisite_is_not_checked_by_devkit_itself() -> None:
    """devkit parses and release-gates options only; the template's validator is authoritative."""
    published = ResolvedTemplate(location="https://example.invalid/t.git", ref="v0.3.0", mode="published", local_root=None)
    assert parse_options(SPEC, ["forms=true"]) == {"forms": True}  # accepted without zod
    ensure_options_available(SPEC, {"forms": True}, published)  # and offline validation raises nothing


# ------------------------------------------------------------------ generation


def test_the_default_release_is_the_newest_supported_and_forms_with_zod_generates(world) -> None:
    _, _, out = world
    result = generate_project(NewRequest("forms-app", output_dir=out, options=("zod=true", "forms=true")))
    assert result.template.ref == "v0.3.1"
    assert flags(result.destination) == ["cache_components=true", "zod=true", "forms=true"]
    recorded = answers(result.destination)
    assert (recorded["zod"], recorded["forms"], recorded["_commit"]) == (True, True, "v0.3.1")


def test_without_options_forms_stays_off(world) -> None:
    _, _, out = world
    project = generate_project(NewRequest("plain", output_dir=out)).destination
    assert answers(project)["forms"] is False and flags(project)[-1] == "forms=false"


@pytest.mark.parametrize("options", [("forms=true",), ("forms=true", "zod=false"), ("forms=yes",)], ids=str)
def test_forms_without_zod_is_rejected_by_the_template_before_anything_is_created(world, options) -> None:
    _, _, out = world
    with pytest.raises(UsageError, match="forms requires zod") as raised:
        generate_project(NewRequest("app", output_dir=out, options=options))
    assert raised.value.exit_code == 2
    assert entries(out) == []


def test_the_rejection_is_exit_code_2_through_the_command_line(world, capsys) -> None:
    _, _, out = world
    code = cli.main(["new", "app", "--set", "forms=true", "--output-dir", str(out)])
    assert code == 2
    assert "forms requires zod" in capsys.readouterr().err
    assert entries(out) == []


def test_a_dry_run_reports_the_same_rejection_and_creates_nothing(world) -> None:
    _, _, out = world
    with pytest.raises(UsageError, match="forms requires zod"):
        generate_project(NewRequest("app", output_dir=out, options=("forms=true",), dry_run=True))
    assert entries(out) == []


@pytest.mark.parametrize("tag", ["v0.1.0", "v0.1.1", "v0.2.0", "v0.2.1"])
def test_forms_cannot_be_requested_from_template_0_2_x_or_earlier(world, tag: str) -> None:
    _, _, out = world
    with pytest.raises(UsageError, match=rf"'forms' needs template v0\.3\.0 or newer, but release {tag}") as raised:
        generate_project(NewRequest("app", output_dir=out, template_ref=tag, options=("forms=true",)))
    assert raised.value.exit_code == 2
    assert entries(out) == []


def test_zod_and_forms_together_are_refused_for_a_release_that_has_neither(world) -> None:
    _, _, out = world
    with pytest.raises(UsageError, match="'zod' needs template v0.2.0 or newer, but release v0.1.1"):
        generate_project(NewRequest("app", output_dir=out, template_ref="v0.1.1", options=("zod=true", "forms=true")))
    assert entries(out) == []


def test_the_refusal_for_an_old_release_is_exit_code_2_on_the_command_line(world, capsys) -> None:
    _, _, out = world
    code = cli.main(["new", "app", "--template-ref", "v0.2.1", "--set", "zod=true", "--set", "forms=true", "--output-dir", str(out)])
    assert code == 2
    assert "needs template v0.3.0" in capsys.readouterr().err
    assert entries(out) == []


def test_the_first_release_with_forms_accepts_it(world) -> None:
    _, _, out = world
    project = generate_project(NewRequest("edge", output_dir=out, template_ref="v0.3.0", options=("zod=true", "forms=true"))).destination
    assert answers(project)["forms"] is True and answers(project)["_commit"] == "v0.3.0"


@pytest.mark.parametrize("tag", ["v0.1.0", "v0.2.0", "v0.2.1", "v0.3.0"])
def test_every_supported_release_still_generates_with_the_options_it_has(world, tag: str) -> None:
    _, _, out = world
    project = generate_project(NewRequest("app", output_dir=out, template_ref=tag)).destination
    assert answers(project)["_commit"] == tag
    assert ("forms" in answers(project)) == (tag == "v0.3.0")


@pytest.mark.parametrize("option", ["forms=banana", "forms=maybe", "forms="], ids=str)
def test_an_invalid_forms_value_is_refused_before_creation(world, option: str) -> None:
    _, _, out = world
    with pytest.raises(UsageError):
        generate_project(NewRequest("app", output_dir=out, options=("zod=true", option)))
    assert entries(out) == []


# ------------------------------------------------------------------ the supported range


def test_a_release_outside_the_range_is_never_selected_or_accepted(world) -> None:
    repo, remote, out = world
    release(repo, "v0.4.0")
    publish(repo, remote, "v0.4.0")
    newest = generate_project(NewRequest("default", output_dir=out)).destination
    assert answers(newest)["_commit"] == "v0.3.1"  # the newer, unsupported release is skipped
    with pytest.raises(UsageError, match="outside the range this devkit supports"):
        generate_project(NewRequest("pinned", output_dir=out, template_ref="v0.4.0"))
    assert entries(out) == ["default"]


def test_the_range_covers_exactly_0_1_0_up_to_but_excluding_0_4_0() -> None:
    assert str(SPEC.versions) == ">=0.1.0,<0.4.0"
    assert SPEC.versions.contains((0, 1, 0)) and SPEC.versions.contains((0, 3, 99))
    assert not SPEC.versions.contains((0, 0, 9)) and not SPEC.versions.contains((0, 4, 0))


# ------------------------------------------------------------------ upgrades


def test_existing_projects_keep_their_selections_and_user_work_when_upgraded_to_0_3(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.2.0", "zod=true", "cache_components=false")
    commit = head(project)

    result = upgrade(project)

    assert result.changed and result.plan.target == (0, 3, 1)
    recorded = answers(project)
    assert (recorded["zod"], recorded["cache_components"], recorded["_commit"]) == (True, False, "v0.3.1")
    assert recorded["forms"] is False  # a feature the new release introduces stays off
    assert flags(project) == ["cache_components=false", "zod=true", "forms=false"]
    assert (project / "notes.txt").read_text() == "my own file\n"
    assert "Local note." in (project / "README.md").read_text()
    assert head(project) == commit


def test_forms_can_be_enabled_on_an_existing_zod_project_and_user_changes_survive(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.3.1", "zod=true")
    commit = head(project)
    (project / "notes.txt").write_text("my own file\nedited after the commit\n")  # uncommitted: must be refused...
    with pytest.raises(OperationError, match="uncommitted"):
        upgrade(project, options=("forms=true",))
    run_git(project, "add", "-A")
    run_git(project, "commit", "-q", "-m", "user edit")  # ...so commit it, as the documented workflow says
    commit = head(project)

    result = upgrade(project, options=("forms=true",))

    assert result.changed and result.plan.options == {"forms": True}
    assert (answers(project)["zod"], answers(project)["forms"]) == (True, True)
    assert flags(project) == ["cache_components=true", "zod=true", "forms=true"]
    assert (project / "notes.txt").read_text() == "my own file\nedited after the commit\n"
    assert "Local note." in (project / "README.md").read_text()
    assert head(project) == commit


def test_forms_can_be_enabled_in_the_same_step_that_upgrades_from_0_2(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.2.1", "zod=true")
    result = upgrade(project, options=("forms=true",))
    assert result.plan.target == (0, 3, 1)
    assert (answers(project)["zod"], answers(project)["forms"], answers(project)["_commit"]) == (True, True, "v0.3.1")
    assert (project / "notes.txt").read_text() == "my own file\n"


def test_enabling_forms_without_zod_on_an_existing_project_fails_safely(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.3.0")  # no zod
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError, match="forms requires zod") as raised:
        upgrade(project, options=("forms=true",))
    assert raised.value.exit_code == 2
    assert_untouched(project, before, commit)
    assert answers(project)["zod"] is False


def test_enabling_forms_while_the_target_release_lacks_it_is_refused(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.2.0", "zod=true")
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError, match="'forms' needs template v0.3.0 or newer, but release v0.2.1"):
        upgrade(project, to="v0.2.1", options=("forms=true",))
    assert_untouched(project, before, commit)


@pytest.mark.parametrize("option", ["forms=banana", "forms", "forms=2"], ids=str)
def test_invalid_forms_values_fail_an_upgrade_safely(world, option: str) -> None:
    _, _, out = world
    project = project_at(out, "v0.3.0", "zod=true")
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError):
        upgrade(project, options=(option,))
    assert_untouched(project, before, commit)


def test_upgrade_targets_outside_the_range_are_refused_and_change_nothing(world) -> None:
    repo, remote, out = world
    release(repo, "v0.4.0")
    publish(repo, remote, "v0.4.0")
    project = project_at(out, "v0.3.0", "zod=true")
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError, match="outside the range"):
        upgrade(project, to="v0.4.0")
    assert_untouched(project, before, commit)
    assert upgrade(project).plan.target == (0, 3, 1)  # the newest supported release, not v0.4.0


def test_a_project_from_a_release_newer_than_this_devkit_supports_is_refused(world, point_profile_at) -> None:
    _, _, out = world
    project = project_at(out, "v0.3.0", "zod=true")
    before, commit = snapshot(project), head(project)
    point_profile_at(answers(project)["_src_path"], versions=((0, 1, 0), (0, 3, 0)))  # a devkit that predates forms
    with pytest.raises(UsageError, match="newer than this devkit supports"):
        upgrade(project)
    assert_untouched(project, before, commit)
