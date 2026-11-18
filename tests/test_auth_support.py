"""devkit 0.7 supports template releases 0.1.x to 0.6.x and offers `auth` from template 0.6.0.

`auth` is a boolean whose prerequisites (zod, rest_api and a database) are enforced by the template's own
validator: devkit must not duplicate them. It knows which release first has the option, and that an
established selection is something `upgrade` may not undo. The versioned mini template mirrors the real
history. After every refusal nothing may have been created or changed.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

import devkit
from conftest import PLATFORM_ROOT, make_remote, make_versioned_template, publish, release, run_git
from devkit import cli
from devkit.errors import UsageError
from devkit.generate import NewRequest, generate_project
from devkit.profiles import PROFILES
from devkit.sources import ResolvedTemplate
from devkit.validation import ensure_options_available, parse_options
from test_database_support import answers, assert_untouched, entries, flags, head, project_at, snapshot, upgrade

SPEC = PROFILES["web-core"].template
OPTION = next(o for o in SPEC.options if o.name == "auth")
ALL = ("zod=true", "rest_api=true", "database=postgres", "auth=true")


@pytest.fixture()
def world(tmp_path, point_profile_at, https_origin):
    """(repo, remote, out): v0.1.0 to v0.6.1 published; the registry supports >=0.1.0,<0.7.0."""
    repo = make_versioned_template(tmp_path / "work" / "web-core-template", through_auth=True)
    remote = make_remote(repo, tmp_path / "remote" / "web-core-template.git")
    point_profile_at(https_origin(remote), versions=((0, 1, 0), (0, 7, 0)))
    out = tmp_path / "out"
    out.mkdir()
    return repo, remote, out


# ------------------------------------------------------------------ the registry, validation and version


def test_auth_is_a_boolean_that_defaults_to_off_and_starts_at_template_0_6_0() -> None:
    assert OPTION.kind == "bool" and OPTION.default is False and OPTION.since == (0, 6, 0) and OPTION.choices == ()
    assert OPTION.sticky is True and "zod" in OPTION.help and "rest_api" in OPTION.help and "database" in OPTION.help
    assert not hasattr(OPTION, "requires")  # the prerequisites are described, never encoded as a rule here
    assert "docs/auth.md" in OPTION.sticky_reason


def test_the_registry_after_auth_keeps_every_earlier_option_exactly() -> None:
    assert [(o.name, o.since, o.default) for o in SPEC.options] == [
        ("cache_components", (0, 1, 0), True), ("zod", (0, 2, 0), False), ("forms", (0, 3, 0), False),
        ("rest_api", (0, 4, 0), False), ("database", (0, 5, 0), "none"), ("auth", (0, 6, 0), False),
    ]  # fmt: skip


def test_the_range_is_0_1_0_up_to_but_excluding_0_7_0() -> None:
    assert str(SPEC.versions) == ">=0.1.0,<0.7.0"
    assert SPEC.versions.contains((0, 1, 0)) and SPEC.versions.contains((0, 6, 99))
    assert not SPEC.versions.contains((0, 0, 9)) and not SPEC.versions.contains((0, 7, 0))


def test_the_version_is_reported_consistently_and_matches_the_package_metadata(capsys) -> None:
    pyproject = tomllib.loads((PLATFORM_ROOT / "pyproject.toml").read_text())
    assert devkit.__version__ == pyproject["project"]["version"] == "0.7.0"
    with pytest.raises(SystemExit) as exited:
        cli.main(["--version"])
    assert exited.value.code == 0
    assert capsys.readouterr().out.strip() == "devkit 0.7.0"


@pytest.mark.parametrize(("raw", "value"), [("true", True), ("false", False), ("yes", True), ("no", False), ("on", True), ("off", False), ("1", True), ("0", False)])
def test_boolean_spellings_parse(raw: str, value: bool) -> None:
    assert parse_options(SPEC, [f"auth={raw}"]) == {"auth": value}


@pytest.mark.parametrize("raw", ["banana", "", "2", "maybe"])
def test_anything_else_is_refused_before_a_template_is_touched(raw: str) -> None:
    with pytest.raises(UsageError, match="Option 'auth' is true/false") as raised:
        parse_options(SPEC, [f"auth={raw}"])
    assert raised.value.exit_code == 2


def test_the_prerequisites_are_not_checked_by_devkit_itself() -> None:
    published = ResolvedTemplate(location="https://example.invalid/t.git", ref="v0.6.0", mode="published", local_root=None)
    assert parse_options(SPEC, ["auth=true"]) == {"auth": True}  # accepted without zod, rest_api or a database
    ensure_options_available(SPEC, {"auth": True}, published)  # and offline validation raises nothing


# ------------------------------------------------------------------ generation


@pytest.mark.parametrize("provider", ["postgres", "supabase"])
def test_auth_with_its_prerequisites_generates_with_the_default_release_and_is_recorded(world, provider: str) -> None:
    _, _, out = world
    result = generate_project(NewRequest(f"{provider}-app", output_dir=out, options=("zod=true", "rest_api=true", f"database={provider}", "auth=true")))
    assert result.template.ref == "v0.6.1"
    recorded = answers(result.destination)
    assert (recorded["auth"], recorded["database"], recorded["rest_api"], recorded["zod"], recorded["forms"], recorded["_commit"]) == (True, provider, True, True, False, "v0.6.1")
    assert flags(result.destination)[-1] == "auth=true"


def test_auth_works_with_and_without_forms(world) -> None:
    _, _, out = world
    for forms in (False, True):
        project = generate_project(NewRequest(f"forms-{str(forms).lower()}", output_dir=out, options=(*ALL, f"forms={str(forms).lower()}"))).destination
        assert (answers(project)["auth"], answers(project)["forms"]) == (True, forms)


def test_without_options_auth_stays_off_and_false_is_the_same_as_omitting_it(world) -> None:
    _, _, out = world
    default = generate_project(NewRequest("plain", output_dir=out)).destination
    explicit = generate_project(NewRequest("explicit", output_dir=out, options=("auth=false",))).destination
    assert answers(default)["auth"] is False and answers(explicit)["auth"] is False
    assert flags(default)[-1] == "auth=false"


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (("auth=true",), "auth requires zod"),
        (("zod=true", "auth=true"), "auth requires rest_api"),
        (("zod=true", "database=postgres", "auth=true"), "auth requires rest_api"),
        (("zod=true", "rest_api=true", "auth=true"), "auth requires a database"),
        (("zod=true", "rest_api=true", "forms=true", "database=none", "auth=true"), "auth requires a database"),
        (("rest_api=false", "zod=true", "database=supabase", "auth=true"), "auth requires rest_api"),
    ],
    ids=str,
)
def test_missing_prerequisites_are_rejected_by_the_template_before_anything_is_created(world, options, message: str) -> None:
    _, _, out = world
    with pytest.raises(UsageError, match=message) as raised:
        generate_project(NewRequest("app", output_dir=out, options=options))
    assert raised.value.exit_code == 2
    assert entries(out) == []


def test_the_rejection_is_exit_code_2_through_the_command_line_and_in_a_dry_run(world, capsys) -> None:
    _, _, out = world
    assert cli.main(["new", "app", "--set", "zod=true", "--set", "database=postgres", "--set", "auth=true", "--output-dir", str(out)]) == 2
    assert "auth requires rest_api" in capsys.readouterr().err
    with pytest.raises(UsageError, match="auth requires zod"):
        generate_project(NewRequest("app", output_dir=out, options=("auth=true",), dry_run=True))
    assert entries(out) == []


@pytest.mark.parametrize("tag", ["v0.1.0", "v0.2.1", "v0.4.1", "v0.5.0", "v0.5.1"])
def test_auth_cannot_be_requested_from_template_0_5_x_or_earlier(world, tag: str) -> None:
    _, _, out = world
    with pytest.raises(UsageError, match=rf"'auth' needs template v0\.6\.0 or newer, but release {tag}") as raised:
        generate_project(NewRequest("app", output_dir=out, template_ref=tag, options=("auth=true",)))
    assert raised.value.exit_code == 2
    assert entries(out) == []


def test_auth_is_accepted_for_the_first_release_that_has_it(world) -> None:
    _, _, out = world
    project = generate_project(NewRequest("edge", output_dir=out, template_ref="v0.6.0", options=ALL)).destination
    assert answers(project)["auth"] is True and answers(project)["_commit"] == "v0.6.0"
    with pytest.raises(UsageError, match="needs template v0.6.0"):
        generate_project(NewRequest("old", output_dir=out, template_ref="v0.5.1", options=("auth=false",)))  # even `false` names a question the release lacks


def test_a_release_outside_the_range_is_never_selected_or_accepted(world) -> None:
    repo, remote, out = world
    release(repo, "v0.7.0")
    publish(repo, remote, "v0.7.0")
    assert answers(generate_project(NewRequest("default", output_dir=out)).destination)["_commit"] == "v0.6.1"
    with pytest.raises(UsageError, match="outside the range this devkit supports"):
        generate_project(NewRequest("pinned", output_dir=out, template_ref="v0.7.0"))
    assert entries(out) == ["default"]


# ------------------------------------------------------------------ upgrades


def test_upgrading_from_template_0_5_keeps_every_selection_and_user_files_and_leaves_auth_off(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.5.0", "zod=true", "forms=true", "rest_api=true", "database=supabase", "cache_components=false")
    commit = head(project)

    result = upgrade(project)

    assert result.changed and result.plan.target == (0, 6, 1)
    recorded = answers(project)
    assert (recorded["zod"], recorded["forms"], recorded["rest_api"], recorded["database"], recorded["cache_components"], recorded["_commit"]) == (True, True, True, "supabase", False, "v0.6.1")
    assert recorded["auth"] is False  # a feature the new release introduces stays off
    assert (project / "notes.txt").read_text() == "my own file\n" and "Local note." in (project / "README.md").read_text()
    assert head(project) == commit


@pytest.mark.parametrize("provider", ["postgres", "supabase"])
def test_auth_can_be_enabled_on_an_existing_database_project_and_user_changes_survive(world, provider: str) -> None:
    _, _, out = world
    project = project_at(out, "v0.6.0", "zod=true", "rest_api=true", f"database={provider}")
    (project / "notes.txt").write_text("my own file\nedited after the commit\n")
    run_git(project, "add", "-A")
    run_git(project, "commit", "-q", "-m", "user edit")
    commit = head(project)

    result = upgrade(project, options=("auth=true",))

    assert result.changed and result.plan.options == {"auth": True}
    assert (answers(project)["auth"], answers(project)["database"], answers(project)["rest_api"]) == (True, provider, True)
    assert flags(project)[-1] == "auth=true"
    assert (project / "notes.txt").read_text() == "my own file\nedited after the commit\n" and "Local note." in (project / "README.md").read_text()
    assert head(project) == commit


def test_auth_can_be_enabled_in_the_same_step_that_upgrades_from_0_5_and_keeps_the_other_features(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.5.1", "zod=true", "forms=true", "rest_api=true", "database=postgres")
    result = upgrade(project, options=("auth=true",))
    assert result.plan.target == (0, 6, 1)
    recorded = answers(project)
    assert (recorded["zod"], recorded["forms"], recorded["rest_api"], recorded["database"], recorded["auth"], recorded["_commit"]) == (True, True, True, "postgres", True, "v0.6.1")
    assert (project / "notes.txt").read_text() == "my own file\n"


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        (("zod=true", "rest_api=true"), "auth requires a database"),
        (("zod=true", "database=postgres"), "auth requires rest_api"),
        ((), "auth requires zod"),
    ],
    ids=["no database", "no rest_api", "nothing"],
)
def test_enabling_auth_without_its_prerequisites_on_an_existing_project_fails_safely(world, setup, message: str) -> None:
    _, _, out = world
    project = project_at(out, "v0.6.0", *setup)
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError, match=message) as raised:
        upgrade(project, options=("auth=true",))
    assert raised.value.exit_code == 2
    assert_untouched(project, before, commit)
    assert answers(project)["auth"] is False


def test_enabling_auth_while_the_target_release_lacks_it_is_refused(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.5.0", "zod=true", "rest_api=true", "database=postgres")
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError, match="'auth' needs template v0.6.0 or newer, but release v0.5.1"):
        upgrade(project, to="v0.5.1", options=("auth=true",))
    assert_untouched(project, before, commit)


@pytest.mark.parametrize("option", ["auth=banana", "auth=", "auth", "auth=2"], ids=str)
def test_an_invalid_value_fails_an_upgrade_safely(world, option: str) -> None:
    _, _, out = world
    project = project_at(out, "v0.6.0", *ALL)
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError):
        upgrade(project, options=(option,))
    assert_untouched(project, before, commit)


# ------------------------------------------------------------------ an established selection is not undone by upgrade


@pytest.mark.parametrize("off", ["false", "no", "off", "0"])
def test_disabling_established_auth_is_refused_and_changes_nothing(world, off: str) -> None:
    _, _, out = world
    project = project_at(out, "v0.6.0", *ALL)
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError, match="auth is 'true' in this project; changing it to 'false' is not an upgrade") as raised:
        upgrade(project, options=(f"auth={off}",))
    assert raised.value.exit_code == 2
    assert "not automated" in str(raised.value) and "docs/auth.md" in str(raised.value)
    assert_untouched(project, before, commit)
    assert answers(project)["auth"] is True


def test_the_refusal_is_exit_code_2_through_the_command_line(world, capsys) -> None:
    _, _, out = world
    project = project_at(out, "v0.6.0", *ALL)
    before, commit = snapshot(project), head(project)
    assert cli.main(["upgrade", str(project), "--set", "auth=false"]) == 2
    assert "is not an upgrade" in capsys.readouterr().err
    assert_untouched(project, before, commit)


def test_repeating_established_auth_or_upgrading_without_naming_it_is_fine(world) -> None:
    repo, remote, out = world
    project = project_at(out, "v0.6.0", *ALL)
    same = upgrade(project, options=("auth=true",))
    assert same.plan.options == {"auth": True} and answers(project)["auth"] is True
    run_git(project, "add", "-A")
    run_git(project, "commit", "-q", "-m", "re-render")
    release(repo, "v0.6.2")
    publish(repo, remote, "v0.6.2")
    result = upgrade(project)
    assert result.plan.target == (0, 6, 2) and answers(project)["auth"] is True  # kept, not asked again


def test_enabling_from_the_recorded_default_is_not_blocked_by_the_lock(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.6.0", "zod=true", "rest_api=true", "database=postgres")
    assert answers(project)["auth"] is False
    upgrade(project, options=("auth=true",))  # false to true is the whole point, and allowed
    assert answers(project)["auth"] is True


def test_the_database_provider_stays_locked_while_auth_is_on_and_other_options_can_change(world) -> None:
    _, _, out = world
    project = project_at(out, "v0.6.0", *ALL)
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError, match="database is 'postgres' in this project; changing it to 'supabase' is not an upgrade"):
        upgrade(project, options=("database=supabase",))
    assert_untouched(project, before, commit)
    result = upgrade(project, options=("forms=true", "cache_components=false"))
    assert result.changed
    recorded = answers(project)
    assert (recorded["forms"], recorded["cache_components"], recorded["database"], recorded["auth"]) == (True, False, "postgres", True)


def test_only_the_database_provider_and_auth_are_locked() -> None:
    assert [o.name for o in SPEC.options if o.sticky] == ["database", "auth"]
    assert "docs/database.md" in next(o for o in SPEC.options if o.name == "database").sticky_reason


def test_a_project_newer_than_this_devkit_supports_is_refused_and_untouched(world, point_profile_at) -> None:
    _, _, out = world
    project = project_at(out, "v0.6.0", *ALL)
    point_profile_at(answers(project)["_src_path"], versions=((0, 1, 0), (0, 6, 0)))  # a devkit that predates `auth`
    before, commit = snapshot(project), head(project)
    with pytest.raises(UsageError, match="newer than this devkit supports"):
        upgrade(project)
    assert_untouched(project, before, commit)


def test_an_earlier_devkit_range_still_works_for_projects_it_supports(world, point_profile_at) -> None:
    """Existing application compatibility: a v0.5.0 project upgrades under a devkit that stops at 0.5."""
    _, _, out = world
    project = project_at(out, "v0.5.0", "zod=true", "database=postgres")
    point_profile_at(answers(project)["_src_path"], versions=((0, 1, 0), (0, 6, 0)))
    result = upgrade(project)
    assert result.plan.target == (0, 5, 1)
    assert (answers(project)["database"], answers(project)["_commit"]) == ("postgres", "v0.5.1")
