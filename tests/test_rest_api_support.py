"""devkit 0.5 supports template releases 0.1.x to 0.4.x and offers `rest_api` from template 0.4.0.

The versioned mini template mirrors the real release history: v0.1.x has no `zod`, v0.2.x has it,
v0.3.x adds `forms`, v0.4.x adds `rest_api`. The prerequisite (`zod`) is enforced by the template's own
validator; devkit must not duplicate it, it only knows which release first has the option. After every
refusal nothing may have been created or changed.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import yaml

import devkit
from conftest import PLATFORM_ROOT, make_remote, make_versioned_template, publish, release, run_git
from devkit import cli
from devkit.errors import OperationError, UsageError
from devkit.generate import NewRequest, generate_project
from devkit.profiles import PROFILES
from devkit.sources import ResolvedTemplate
from devkit.upgrade import UpgradeRequest, upgrade_project
from devkit.validation import ensure_options_available, parse_options

SPEC = PROFILES["web-core"].template
OPTION = next(o for o in SPEC.options if o.name == "rest_api")


@pytest.fixture()
def world(tmp_path, point_profile_at, https_origin):
    """(repo, remote, out): v0.1.0 to v0.4.1 published; the registry supports >=0.1.0,<0.5.0."""
    repo = make_versioned_template(tmp_path / "work" / "web-core-template", through_rest_api=True)
    remote = make_remote(repo, tmp_path / "remote" / "web-core-template.git")
    point_profile_at(https_origin(remote), versions=((0, 1, 0), (0, 5, 0)))
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


# ------------------------------------------------------------------ the registry and the version


def test_rest_api_is_a_boolean_option_that_defaults_off_and_starts_at_template_0_4_0() -> None:
    assert OPTION.name == "rest_api" and OPTION.name.isidentifier()  # named like the other options
    assert (OPTION.kind, OPTION.default, OPTION.since) == ("bool", False, (0, 4, 0))
    assert "zod" in OPTION.help  # the prerequisite is described to the user...
    assert not hasattr(OPTION, "requires")  # ...but never encoded as a rule in devkit


def test_the_range_is_0_1_0_up_to_but_excluding_0_5_0() -> None:
    assert str(SPEC.versions) == ">=0.1.0,<0.5.0"
    assert SPEC.versions.contains((0, 1, 0)) and SPEC.versions.contains((0, 4, 99))
    assert not SPEC.versions.contains((0, 0, 9)) and not SPEC.versions.contains((0, 5, 0))


def test_the_prerequisite_is_not_checked_by_devkit_itself() -> None:
    published = ResolvedTemplate(location="https://example.invalid/t.git", ref="v0.4.0", mode="published", local_root=None)
    assert parse_options(SPEC, ["rest_api=true"]) == {"rest_api": True}  # accepted without zod
    ensure_options_available(SPEC, {"rest_api": True}, published)  # and offline validation raises nothing


def test_the_version_is_reported_consistently_and_matches_the_package_metadata(capsys) -> None:
    pyproject = tomllib.loads((PLATFORM_ROOT / "pyproject.toml").read_text())
    assert devkit.__version__ == pyproject["project"]["version"] == "0.5.0"
    with pytest.raises(SystemExit) as exited:
        cli.main(["--version"])
    assert exited.value.code == 0
    assert capsys.readouterr().out.strip() == "devkit 0.5.0"


# ------------------------------------------------------------------ generation


def test_the_default_release_is_the_newest_supported_and_rest_api_with_zod_generates(world) -> None:
    _, _, out = world
    result = generate_project(NewRequest("api-app", output_dir=out, options=("zod=true", "rest_api=true")))
    assert result.template.ref == "v0.4.1"
    assert flags(result.destination) == ["cache_components=true", "zod=true", "forms=false", "rest_api=true"]
    recorded = answers(result.destination)
    assert (recorded["zod"], recorded["forms"], recorded["rest_api"], recorded["_commit"]) == (True, False, True, "v0.4.1")


def test_rest_api_works_with_and_without_forms_but_always_with_zod(world) -> None:
    _, _, out = world
    without = generate_project(NewRequest("no-forms", output_dir=out, options=("zod=true", "rest_api=true"))).destination
    with_forms = generate_project(NewRequest("with-forms", output_dir=out, options=("zod=true", "forms=true", "rest_api=true"))).destination
    assert [answers(p)["forms"] for p in (without, with_forms)] == [False, True]
    assert all(answers(p)["rest_api"] and answers(p)["zod"] for p in (without, with_forms))
    forms_only = generate_project(NewRequest("forms-only", output_dir=out, options=("zod=true", "forms=true"))).destination
    assert answers(forms_only)["rest_api"] is False and flags(forms_only)[-1] == "rest_api=false"


def test_without_options_rest_api_stays_off(world) -> None:
    _, _, out = world
    project = generate_project(NewRequest("plain", output_dir=out)).destination
    assert answers(project)["rest_api"] is False


@pytest.mark.parametrize("options", [("rest_api=true",), ("rest_api=true", "zod=false"), ("rest_api=yes",), ("forms=false", "rest_api=true")], ids=str)
def test_rest_api_without_zod_is_rejected_by_the_template_before_anything_is_created(world, options) -> None:
    _, _, out = world
    with pytest.raises(UsageError, match="rest_api requires zod") as raised:
        generate_project(NewRequest("app", output_dir=out, options=options))
    assert raised.value.exit_code == 2
    assert entries(out) == []


def test_the_rejection_is_exit_code_2_through_the_command_line_and_in_a_dry_run(world, capsys) -> None:
    _, _, out = world
    assert cli.main(["new", "app", "--set", "rest_api=true", "--output-dir", str(out)]) == 2
    assert "rest_api requires zod" in capsys.readouterr().err
    with pytest.raises(UsageError, match="rest_api requires zod"):
        generate_project(NewRequest("app", output_dir=out, options=("rest_api=true",), dry_run=True))
    assert entries(out) == []


@pytest.mark.parametrize("tag", ["v0.1.0", "v0.1.1", "v0.2.0", "v0.2.1", "v0.3.0", "v0.3.1"])
def test_rest_api_cannot_be_requested_from_template_0_3_x_or_earlier(world, tag: str) -> None:
    _, _, out = world
    with pytest.raises(UsageError, match=rf"'rest_api' needs template v0\.4\.0 or newer, but release {tag}") as raised:
        generate_project(NewRequest("app", output_dir=out, template_ref=tag, options=("rest_api=true",)))
    assert raised.value.exit_code == 2
    assert entries(out) == []


def test_the_refusal_for_an_older_release_is_exit_code_2_on_the_command_line(world, capsys) -> None:
    _, _, out = world
    code = cli.main(["new", "app", "--template-ref", "v0.3.1", "--set", "zod=true", "--set", "rest_api=true", "--output-dir", str(out)])
    assert code == 2
    assert "needs template v0.4.0" in capsys.readouterr().err
    assert entries(out) == []


def test_the_first_release_with_rest_api_accepts_it_and_older_releases_still_generate(world) -> None:
    _, _, out = world
    edge = generate_project(NewRequest("edge", output_dir=out, template_ref="v0.4.0", options=("zod=true", "rest_api=true"))).destination
    assert answers(edge)["rest_api"] is True and answers(edge)["_commit"] == "v0.4.0"
    for tag in ("v0.1.0", "v0.2.1", "v0.3.0"):
        project = generate_project(NewRequest("app-" + tag.replace(".", "-"), output_dir=out, template_ref=tag)).destination
        assert answers(project)["_commit"] == tag and ("rest_api" in answers(project)) is False


@pytest.mark.parametrize("option", ["rest_api=banana", "rest_api=maybe", "rest_api=", "rest-api=true", "rest_api"], ids=str)
def test_an_invalid_rest_api_selection_is_refused_before_creation(world, option: str) -> None:
    _, _, out = world
    with pytest.raises(UsageError):
        generate_project(NewRequest("app", output_dir=out, options=("zod=true", option)))
    assert entries(out) == []


# ------------------------------------------------------------------ the supported range


def test_a_release_outside_the_range_is_never_selected_or_accepted(world) -> None:
    repo, remote, out = world
    release(repo, "v0.5.0")
    publish(repo, remote, "v0.5.0")
    newest = generate_project(NewRequest("default", output_dir=out)).destination
    assert answers(newest)["_commit"] == "v0.4.1"  # the newer, unsupported release is skipped
    with pytest.raises(UsageError, match="outside the range this devkit supports"):
        generate_project(NewRequest("pinned", output_dir=out, template_ref="v0.5.0"))
    assert entries(out) == ["default"]


# ------------------------------------------------------------------ upgrades


def test_upgrading_from_template_0_3_keeps_selections_and_user_files_and_leaves_the_api_off(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.3.0", "zod=true", "forms=true", "cache_components=false")
    commit = head(project)

    result = upgrade(project)

    assert result.changed and result.plan.target == (0, 4, 1)
    recorded = answers(project)
    assert (recorded["zod"], recorded["forms"], recorded["cache_components"], recorded["_commit"]) == (True, True, False, "v0.4.1")
    assert recorded["rest_api"] is False  # a feature the new release introduces stays off
    assert flags(project) == ["cache_components=false", "zod=true", "forms=true", "rest_api=false"]
    assert (project / "notes.txt").read_text() == "my own file\n"
    assert "Local note." in (project / "README.md").read_text()
    assert head(project) == commit


def test_rest_api_can_be_enabled_on_an_existing_zod_project_and_user_changes_survive(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.4.1", "zod=true")
    (project / "notes.txt").write_text("my own file\nedited after the commit\n")
    with pytest.raises(OperationError, match="uncommitted"):  # uncommitted work is refused first...
        upgrade(project, options=("rest_api=true",))
    run_git(project, "add", "-A")
    run_git(project, "commit", "-q", "-m", "user edit")  # ...so commit it, as the documented workflow says
    commit = head(project)

    result = upgrade(project, options=("rest_api=true",))

    assert result.changed and result.plan.options == {"rest_api": True}
    assert (answers(project)["zod"], answers(project)["forms"], answers(project)["rest_api"]) == (True, False, True)
    assert flags(project) == ["cache_components=true", "zod=true", "forms=false", "rest_api=true"]
    assert (project / "notes.txt").read_text() == "my own file\nedited after the commit\n"
    assert "Local note." in (project / "README.md").read_text()
    assert head(project) == commit


def test_rest_api_can_be_enabled_in_the_same_step_that_upgrades_from_0_3_and_keeps_forms(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.3.1", "zod=true", "forms=true")
    result = upgrade(project, options=("rest_api=true",))
    assert result.plan.target == (0, 4, 1)
    recorded = answers(project)
    assert (recorded["zod"], recorded["forms"], recorded["rest_api"], recorded["_commit"]) == (True, True, True, "v0.4.1")
    assert (project / "notes.txt").read_text() == "my own file\n"


def test_enabling_rest_api_without_zod_on_an_existing_project_fails_safely(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.4.0")  # no zod
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError, match="rest_api requires zod") as raised:
        upgrade(project, options=("rest_api=true",))
    assert raised.value.exit_code == 2
    assert_untouched(project, before, commit)
    assert answers(project)["zod"] is False


def test_enabling_rest_api_while_the_target_release_lacks_it_is_refused(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.3.0", "zod=true")
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError, match="'rest_api' needs template v0.4.0 or newer, but release v0.3.1"):
        upgrade(project, to="v0.3.1", options=("rest_api=true",))
    assert_untouched(project, before, commit)


@pytest.mark.parametrize("option", ["rest_api=banana", "rest_api", "rest_api=2", "rest-api=true"], ids=str)
def test_invalid_rest_api_values_fail_an_upgrade_safely(world, option: str) -> None:
    _, _, out = world
    project = project_at(out, "v0.4.0", "zod=true")
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError):
        upgrade(project, options=(option,))
    assert_untouched(project, before, commit)


def test_upgrade_targets_outside_the_range_are_refused_and_change_nothing(world) -> None:
    repo, remote, out = world
    release(repo, "v0.5.0")
    publish(repo, remote, "v0.5.0")
    project = project_at(out, "v0.4.0", "zod=true")
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError, match="outside the range"):
        upgrade(project, to="v0.5.0")
    assert_untouched(project, before, commit)
    assert upgrade(project).plan.target == (0, 4, 1)  # the newest supported release, not v0.5.0


def test_a_project_from_a_release_newer_than_this_devkit_supports_is_refused(world, point_profile_at) -> None:
    _, _, out = world
    project = project_at(out, "v0.4.0", "zod=true")
    before, commit = snapshot(project), head(project)
    point_profile_at(answers(project)["_src_path"], versions=((0, 1, 0), (0, 4, 0)))  # a devkit that predates rest_api
    with pytest.raises(UsageError, match="newer than this devkit supports"):
        upgrade(project)
    assert_untouched(project, before, commit)


def test_an_earlier_devkit_range_still_works_for_projects_it_supports(world, point_profile_at) -> None:
    """Existing application compatibility: a v0.3.0 project upgrades under a devkit that stops at 0.3."""
    _, _, out = world
    project = project_at(out, "v0.3.0", "zod=true", "forms=true")
    point_profile_at(answers(project)["_src_path"], versions=((0, 1, 0), (0, 4, 0)))
    result = upgrade(project)
    assert result.plan.target == (0, 3, 1)
    assert (answers(project)["forms"], answers(project)["_commit"]) == (True, "v0.3.1")
