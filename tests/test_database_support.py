"""devkit 0.6 supports template releases 0.1.x to 0.5.x and offers `database` from template 0.5.0.

`database` is a validated choice (`none`, `postgres`, `supabase`), not a boolean. The versioned mini
template mirrors the real history: v0.5.x adds it, and the template's own validator requires zod. devkit
must not duplicate that rule; it only knows the allowed values, which release first has the option, and
that an established provider is not something `upgrade` may change. After every refusal nothing may have
been created or changed.
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
OPTION = next(o for o in SPEC.options if o.name == "database")


@pytest.fixture()
def world(tmp_path, point_profile_at, https_origin):
    """(repo, remote, out): v0.1.0 to v0.5.1 published; the registry supports >=0.1.0,<0.6.0."""
    repo = make_versioned_template(tmp_path / "work" / "web-core-template", through_database=True)
    remote = make_remote(repo, tmp_path / "remote" / "web-core-template.git")
    point_profile_at(https_origin(remote), versions=((0, 1, 0), (0, 6, 0)))
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


# ------------------------------------------------------------------ the registry, validation and version


def test_database_is_a_closed_choice_that_defaults_to_none_and_starts_at_template_0_5_0() -> None:
    assert OPTION.name == "database" and OPTION.kind == "str" and OPTION.default == "none" and OPTION.since == (0, 5, 0)
    assert OPTION.choices == ("none", "postgres", "supabase") and OPTION.default in OPTION.choices
    assert OPTION.sticky is True and "zod" in OPTION.help  # the prerequisite is described, never encoded as a rule
    assert not hasattr(OPTION, "requires")
    assert [o.name for o in SPEC.options if o.sticky] == ["database", "auth", "native_client"]  # nothing else is locked once chosen


def test_every_release_through_0_5_x_stays_supported() -> None:  # the exact range is pinned in test_auth_support.py
    assert SPEC.versions.contains((0, 1, 0)) and SPEC.versions.contains((0, 5, 0)) and SPEC.versions.contains((0, 5, 99))
    assert not SPEC.versions.contains((0, 0, 9))


@pytest.mark.parametrize("value", ["none", "postgres", "supabase"])
def test_every_declared_value_parses_as_text(value: str) -> None:
    assert parse_options(SPEC, [f"database={value}"]) == {"database": value}


@pytest.mark.parametrize("value", ["oracle", "Postgres", "POSTGRES", "Supabase", "postgres ", " postgres", "", "true", "false", "1", "none ", "mysql", "postgresql"])
def test_any_other_value_is_refused_before_a_template_is_touched(value: str) -> None:
    with pytest.raises(UsageError, match=r"Option 'database' must be one of none, postgres, supabase") as raised:
        parse_options(SPEC, [f"database={value}"])
    assert raised.value.exit_code == 2


def test_the_prerequisite_is_not_checked_by_devkit_itself() -> None:
    published = ResolvedTemplate(location="https://example.invalid/t.git", ref="v0.5.0", mode="published", local_root=None)
    assert parse_options(SPEC, ["database=postgres"]) == {"database": "postgres"}  # accepted without zod
    ensure_options_available(SPEC, {"database": "supabase"}, published)  # and offline validation raises nothing


def test_the_version_is_reported_consistently_and_matches_the_package_metadata(capsys) -> None:
    pyproject = tomllib.loads((PLATFORM_ROOT / "pyproject.toml").read_text())
    assert devkit.__version__ == pyproject["project"]["version"]  # the exact release is pinned in test_auth_support.py
    with pytest.raises(SystemExit) as exited:
        cli.main(["--version"])
    assert exited.value.code == 0
    assert capsys.readouterr().out.strip() == f"devkit {devkit.__version__}"


# ------------------------------------------------------------------ generation


@pytest.mark.parametrize("provider", ["postgres", "supabase"])
def test_a_database_with_zod_generates_with_the_default_release_and_records_the_provider(world, provider: str) -> None:
    _, _, out = world
    result = generate_project(NewRequest(f"{provider}-app", output_dir=out, options=("zod=true", f"database={provider}")))
    assert result.template.ref == "v0.5.1"
    recorded = answers(result.destination)
    assert (recorded["zod"], recorded["database"], recorded["forms"], recorded["rest_api"], recorded["_commit"]) == (True, provider, False, False, "v0.5.1")
    assert flags(result.destination)[-1] == f"database={provider}"


@pytest.mark.parametrize("extra", [(), ("forms=true",), ("rest_api=true",), ("forms=true", "rest_api=true")], ids=lambda e: "+".join(e) or "alone")
def test_a_database_works_with_and_without_forms_and_the_rest_api(world, extra) -> None:
    _, _, out = world
    project = generate_project(NewRequest("combo", output_dir=out, options=("zod=true", "database=postgres", *extra))).destination
    recorded = answers(project)
    assert (recorded["zod"], recorded["database"]) == (True, "postgres")
    assert (recorded["forms"], recorded["rest_api"]) == ("forms=true" in extra, "rest_api=true" in extra)


def test_without_options_the_database_stays_off_and_none_is_the_same_as_omitting_it(world) -> None:
    _, _, out = world
    default = generate_project(NewRequest("plain", output_dir=out)).destination
    explicit = generate_project(NewRequest("explicit", output_dir=out, options=("database=none",))).destination
    assert answers(default)["database"] == "none" == answers(explicit)["database"]
    assert flags(default)[-1] == "database=none"


@pytest.mark.parametrize("options", [("database=postgres",), ("database=supabase",), ("database=postgres", "zod=false"), ("forms=false", "database=supabase")], ids=str)
def test_a_database_without_zod_is_rejected_by_the_template_before_anything_is_created(world, options) -> None:
    _, _, out = world
    with pytest.raises(UsageError, match="database requires zod") as raised:
        generate_project(NewRequest("app", output_dir=out, options=options))
    assert raised.value.exit_code == 2
    assert entries(out) == []


def test_the_rejection_is_exit_code_2_through_the_command_line_and_in_a_dry_run(world, capsys) -> None:
    _, _, out = world
    assert cli.main(["new", "app", "--set", "database=postgres", "--output-dir", str(out)]) == 2
    assert "database requires zod" in capsys.readouterr().err
    with pytest.raises(UsageError, match="database requires zod"):
        generate_project(NewRequest("app", output_dir=out, options=("database=supabase",), dry_run=True))
    assert entries(out) == []


@pytest.mark.parametrize("value", ["oracle", "Postgres", "true", ""], ids=repr)
def test_an_invalid_provider_is_refused_with_exit_code_2_and_creates_nothing(world, capsys, value: str) -> None:
    _, _, out = world
    assert cli.main(["new", "app", "--set", "zod=true", "--set", f"database={value}", "--output-dir", str(out)]) == 2
    assert "must be one of none, postgres, supabase" in capsys.readouterr().err
    assert entries(out) == []


@pytest.mark.parametrize("tag", ["v0.1.0", "v0.2.1", "v0.3.1", "v0.4.0", "v0.4.1"])
def test_a_database_cannot_be_requested_from_template_0_4_x_or_earlier(world, tag: str) -> None:
    _, _, out = world
    with pytest.raises(UsageError, match=rf"'database' needs template v0\.5\.0 or newer, but release {tag}") as raised:
        generate_project(NewRequest("app", output_dir=out, template_ref=tag, options=("database=postgres",)))
    assert raised.value.exit_code == 2
    assert entries(out) == []


def test_database_none_is_accepted_for_the_first_release_that_has_it_but_not_before(world) -> None:
    _, _, out = world
    project = generate_project(NewRequest("edge", output_dir=out, template_ref="v0.5.0", options=("zod=true", "database=supabase"))).destination
    assert answers(project)["database"] == "supabase" and answers(project)["_commit"] == "v0.5.0"
    with pytest.raises(UsageError, match="needs template v0.5.0"):
        generate_project(NewRequest("old", output_dir=out, template_ref="v0.4.1", options=("database=none",)))  # even `none` names a question the release lacks


def test_a_release_outside_the_range_is_never_selected_or_accepted(world) -> None:
    repo, remote, out = world
    release(repo, "v0.6.0")
    publish(repo, remote, "v0.6.0")
    assert answers(generate_project(NewRequest("default", output_dir=out)).destination)["_commit"] == "v0.5.1"
    with pytest.raises(UsageError, match="outside the range this devkit supports"):
        generate_project(NewRequest("pinned", output_dir=out, template_ref="v0.6.0"))
    assert entries(out) == ["default"]


# ------------------------------------------------------------------ upgrades


def test_upgrading_from_template_0_4_keeps_every_selection_and_user_files_and_leaves_the_database_off(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.4.0", "zod=true", "forms=true", "rest_api=true", "cache_components=false")
    commit = head(project)

    result = upgrade(project)

    assert result.changed and result.plan.target == (0, 5, 1)
    recorded = answers(project)
    assert (recorded["zod"], recorded["forms"], recorded["rest_api"], recorded["cache_components"], recorded["_commit"]) == (True, True, True, False, "v0.5.1")
    assert recorded["database"] == "none"  # a feature the new release introduces stays off
    assert (project / "notes.txt").read_text() == "my own file\n" and "Local note." in (project / "README.md").read_text()
    assert head(project) == commit


@pytest.mark.parametrize("provider", ["postgres", "supabase"])
def test_a_database_can_be_enabled_on_an_existing_zod_project_and_user_changes_survive(world, provider: str) -> None:
    _, _, out = world
    project = project_at(out, "v0.5.1", "zod=true")
    (project / "notes.txt").write_text("my own file\nedited after the commit\n")
    with pytest.raises(OperationError, match="uncommitted"):  # uncommitted work is refused first...
        upgrade(project, options=(f"database={provider}",))
    run_git(project, "add", "-A")
    run_git(project, "commit", "-q", "-m", "user edit")  # ...so commit it, as the documented workflow says
    commit = head(project)

    result = upgrade(project, options=(f"database={provider}",))

    assert result.changed and result.plan.options == {"database": provider}
    assert (answers(project)["zod"], answers(project)["database"]) == (True, provider)
    assert flags(project)[-1] == f"database={provider}"
    assert (project / "notes.txt").read_text() == "my own file\nedited after the commit\n" and "Local note." in (project / "README.md").read_text()
    assert head(project) == commit


def test_a_database_can_be_enabled_in_the_same_step_that_upgrades_from_0_4_and_keeps_the_other_features(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.4.1", "zod=true", "forms=true", "rest_api=true")
    result = upgrade(project, options=("database=supabase",))
    assert result.plan.target == (0, 5, 1)
    recorded = answers(project)
    assert (recorded["zod"], recorded["forms"], recorded["rest_api"], recorded["database"], recorded["_commit"]) == (True, True, True, "supabase", "v0.5.1")
    assert (project / "notes.txt").read_text() == "my own file\n"


def test_enabling_a_database_without_zod_on_an_existing_project_fails_safely(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.5.0")
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError, match="database requires zod") as raised:
        upgrade(project, options=("database=postgres",))
    assert raised.value.exit_code == 2
    assert_untouched(project, before, commit)
    assert answers(project)["zod"] is False and answers(project)["database"] == "none"


def test_enabling_a_database_while_the_target_release_lacks_it_is_refused(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.4.0", "zod=true")
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError, match="'database' needs template v0.5.0 or newer, but release v0.4.1"):
        upgrade(project, to="v0.4.1", options=("database=postgres",))
    assert_untouched(project, before, commit)


@pytest.mark.parametrize("option", ["database=oracle", "database=Postgres", "database=", "database", "database=true"], ids=str)
def test_an_invalid_provider_fails_an_upgrade_safely(world, option: str) -> None:
    _, _, out = world
    project = project_at(out, "v0.5.0", "zod=true")
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError):
        upgrade(project, options=(option,))
    assert_untouched(project, before, commit)


# ------------------------------------------------------------------ an established provider is not an upgrade


@pytest.mark.parametrize(("installed", "requested"), [("postgres", "supabase"), ("supabase", "postgres"), ("postgres", "none"), ("supabase", "none")])
def test_changing_an_established_provider_is_refused_and_changes_nothing(world, installed: str, requested: str) -> None:
    _, _, out = world
    project = project_at(out, "v0.5.0", "zod=true", f"database={installed}")
    before, commit = snapshot(project), head(project)

    with pytest.raises(UsageError, match=rf"database is '{installed}' in this project; changing it to '{requested}' is not an upgrade") as raised:
        upgrade(project, options=(f"database={requested}",))

    assert raised.value.exit_code == 2
    assert "moving data between providers is not automated" in str(raised.value) and "docs/database.md" in str(raised.value)
    assert_untouched(project, before, commit)
    assert answers(project)["database"] == installed


def test_the_refusal_is_exit_code_2_through_the_command_line_even_with_a_newer_release_available(world, capsys) -> None:
    _, _, out = world
    project = project_at(out, "v0.4.1", "zod=true")
    upgrade(project, options=("database=postgres",))  # enabling from none is fine
    run_git(project, "add", "-A")
    run_git(project, "commit", "-q", "-m", "adopt the database")
    before, commit = snapshot(project), head(project)
    assert cli.main(["upgrade", str(project), "--set", "database=supabase"]) == 2
    assert "is not an upgrade" in capsys.readouterr().err
    assert_untouched(project, before, commit)


def test_repeating_the_established_provider_or_upgrading_without_naming_it_is_fine(world) -> None:
    repo, remote, out = world
    project = project_at(out, "v0.5.0", "zod=true", "database=supabase")
    same = upgrade(project, options=("database=supabase",))
    assert same.plan.options == {"database": "supabase"} and answers(project)["database"] == "supabase"
    run_git(project, "add", "-A")
    run_git(project, "commit", "-q", "-m", "re-render")
    release(repo, "v0.5.2")
    publish(repo, remote, "v0.5.2")
    result = upgrade(project)
    assert result.plan.target == (0, 5, 2) and answers(project)["database"] == "supabase"  # kept, not asked again


def test_only_the_provider_is_locked_other_options_can_still_be_changed_by_upgrade(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.5.0", "zod=true", "database=postgres")
    result = upgrade(project, options=("forms=true", "cache_components=false"))
    assert result.changed
    recorded = answers(project)
    assert (recorded["forms"], recorded["cache_components"], recorded["database"]) == (True, False, "postgres")


def test_upgrade_targets_outside_the_range_and_newer_projects_are_refused_and_change_nothing(world, point_profile_at) -> None:
    repo, remote, out = world
    release(repo, "v0.6.0")
    publish(repo, remote, "v0.6.0")
    project = project_at(out, "v0.5.0", "zod=true")
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError, match="outside the range"):
        upgrade(project, to="v0.6.0")
    assert_untouched(project, before, commit)
    assert upgrade(project).plan.target == (0, 5, 1)
    run_git(project, "add", "-A")
    run_git(project, "commit", "-q", "-m", "upgraded")
    point_profile_at(answers(project)["_src_path"], versions=((0, 1, 0), (0, 5, 0)))  # a devkit that predates `database`
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError, match="newer than this devkit supports"):
        upgrade(project)
    assert_untouched(project, before, commit)


def test_an_earlier_devkit_range_still_works_for_projects_it_supports(world, point_profile_at) -> None:
    """Existing application compatibility: a v0.4.0 project upgrades under a devkit that stops at 0.4."""
    _, _, out = world
    project = project_at(out, "v0.4.0", "zod=true", "forms=true", "rest_api=true")
    point_profile_at(answers(project)["_src_path"], versions=((0, 1, 0), (0, 5, 0)))
    result = upgrade(project)
    assert result.plan.target == (0, 4, 1)
    assert (answers(project)["forms"], answers(project)["rest_api"], answers(project)["_commit"]) == (True, True, "v0.4.1")
