"""devkit 0.8: the `full-stack` and `native-ios` profiles, the native layer as a second template, and layered upgrades.

The versioned mini templates mirror the real history (web 0.1.x to 0.7.x; native 0.1.x). Everything below is offline.
After every refusal nothing may have been created or changed.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import yaml

import devkit
from conftest import PLATFORM_ROOT, make_native_repo, make_remote, make_versioned_template, release, run_git
from devkit import cli
from devkit.errors import UsageError
from devkit.generate import NewRequest, apply_profile_options, generate_project
from devkit.layers import AddNativeRequest, add_native_layer, layer_statuses, pair_problem
from devkit.profiles import NATIVE_REQUIRES_WEB, NATIVE_TEMPLATE, PROFILES, native_requirement
from devkit.upgrade import UpgradeRequest, upgrade_project

WEB_ANSWERS, IOS_ANSWERS = ".copier-answers.yml", ".copier-answers.ios.yml"
CHOICES = ("--set", "database=postgres")


@pytest.fixture()
def world(tmp_path, point_layers_at):
    """(web repo, web remote, native repo, native remote, out): web v0.1.0..v0.7.1, native v0.1.0 and v0.1.1."""
    web = make_versioned_template(tmp_path / "work" / "web-core-template", through_native=True)
    web_remote = make_remote(web, tmp_path / "remote" / "web-core-template.git")
    native = make_native_repo(tmp_path / "work" / "native-ios-template")
    native_remote = make_remote(native, tmp_path / "remote" / "native-ios-template.git")
    point_layers_at(str(web_remote), str(native_remote))
    out = tmp_path / "out"
    out.mkdir()
    return web, web_remote, native, native_remote, out


def answers(project: Path, name: str = WEB_ANSWERS) -> dict:
    return yaml.safe_load((project / name).read_text())


def commit(project: Path, message: str = "work") -> None:
    if not (project / ".git").exists():
        run_git(project, "init", "-q", "-b", "main")
    run_git(project, "add", "-A")
    run_git(project, "commit", "-q", "-m", message)


def new(out: Path, name: str, *args: str) -> int:
    return cli.main(["new", name, "--output-dir", str(out), *args])


def tree(path: Path) -> dict[str, bytes]:
    return {str(p.relative_to(path)): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file() and ".git" not in p.relative_to(path).parts}


# ------------------------------------------------------------------ the registry


def test_the_three_profiles_are_available_and_the_web_range_now_ends_before_0_8_0() -> None:
    assert [(p.id, p.available) for p in PROFILES.values()] == [("web-core", True), ("full-stack", True), ("native-ios", True)]
    assert str(PROFILES["web-core"].template.versions) == ">=0.1.0,<0.8.0"
    option = next(o for o in PROFILES["web-core"].template.options if o.name == "native_client")
    assert (option.kind, option.default, option.since, option.sticky) == ("bool", False, (0, 7, 0), True) and "docs/native-client.md" in option.sticky_reason


def test_full_stack_fixes_the_baseline_and_requires_an_explicit_database_and_native_ios_adds_the_client() -> None:
    full, native = PROFILES["full-stack"], PROFILES["native-ios"]
    assert dict(full.fixed) == {"zod": True, "rest_api": True, "auth": True} and full.required == ("database",) and full.native is None
    assert dict(native.fixed) == {"zod": True, "rest_api": True, "auth": True, "native_client": True} and native.required == ("database",)
    assert native.native is NATIVE_TEMPLATE and NATIVE_TEMPLATE.answers_file == IOS_ANSWERS
    assert "forms" not in dict(full.fixed)  # Forms stays optional


def test_the_native_template_has_its_own_range_origin_and_answers_file() -> None:
    assert str(NATIVE_TEMPLATE.versions) == ">=0.1.0,<0.2.0" and NATIVE_TEMPLATE.url.endswith("/native-ios-template.git")
    assert NATIVE_TEMPLATE.answers_file != PROFILES["web-core"].template.answers_file
    assert {o.name for o in NATIVE_TEMPLATE.options} == {"app_display_name", "bundle_identifier", "debug_api_port", "release_api_host"}


def test_a_native_release_names_the_web_releases_it_was_generated_against() -> None:
    assert str(NATIVE_REQUIRES_WEB[(0, 1)]) == ">=0.7.0,<0.8.0"
    assert native_requirement((0, 1, 5)) is NATIVE_REQUIRES_WEB[(0, 1)] and native_requirement((0, 9, 0)) is None


def test_version_numbers_agree_and_this_is_devkit_0_8_0() -> None:
    assert devkit.__version__ == "0.8.0"
    assert tomllib.loads((PLATFORM_ROOT / "pyproject.toml").read_text())["project"]["version"] == "0.8.0"


def test_profile_options_are_fixed_or_required_never_silently_chosen() -> None:
    profile = PROFILES["native-ios"]
    assert apply_profile_options(profile, {"database": "supabase", "forms": True}) == {"database": "supabase", "forms": True, "zod": True, "rest_api": True, "auth": True, "native_client": True}
    assert apply_profile_options(profile, {"database": "postgres", "auth": True})["auth"] is True  # saying the same thing is fine
    for given, message in (({"database": "postgres", "auth": False}, "contradicts"), ({}, "explicit choice"), ({"database": "none"}, "explicit choice")):
        with pytest.raises(UsageError, match=message):
            apply_profile_options(profile, given)


# ------------------------------------------------------------------ devkit new


def test_full_stack_generates_the_baseline_with_the_chosen_database_and_no_native_layer(world, capsys) -> None:
    *_, out = world
    assert new(out, "fs-app", "--profile", "full-stack", *CHOICES) == 0
    project = out / "fs-app"
    recorded = answers(project)
    assert (recorded["zod"], recorded["rest_api"], recorded["auth"], recorded["database"], recorded["native_client"]) == (True, True, True, "postgres", False)
    assert recorded["_commit"] == "v0.7.1" and not (project / "ios").exists() and not (project / IOS_ANSWERS).exists()


def test_full_stack_keeps_forms_optional(world) -> None:
    *_, out = world
    assert new(out, "fs-forms", "--profile", "full-stack", "--set", "database=supabase", "--set", "forms=true") == 0
    assert answers(out / "fs-forms")["forms"] is True


@pytest.mark.parametrize(
    ("extra", "message"),
    [([], "explicit choice"), (["--set", "database=none"], "explicit choice"), (["--set", "database=postgres", "--set", "auth=false"], "contradicts"),
     (["--set", "database=postgres", "--set", "rest_api=false"], "contradicts"), (["--set", "database=mysql"], "must be one of")],
)  # fmt: skip
def test_full_stack_refuses_what_it_does_not_mean_and_creates_nothing(world, capsys, extra: list[str], message: str) -> None:
    *_, out = world
    assert new(out, "bad-fs", "--profile", "full-stack", *extra) == 2
    assert message in capsys.readouterr().err and not (out / "bad-fs").exists() and list(out.iterdir()) == []


def test_native_ios_builds_both_layers_in_one_directory_with_separate_records(world, capsys) -> None:
    *_, out = world
    assert new(out, "nat-app", "--profile", "native-ios", *CHOICES, "--native-set", "bundle_identifier=org.acme.nat", "--native-set", "debug_api_port=4100") == 0
    project = out / "nat-app"
    web, ios = answers(project), answers(project, IOS_ANSWERS)
    assert web["_commit"] == "v0.7.1" and web["native_client"] is True and web["auth"] is True and web["database"] == "postgres"
    assert ios["_commit"] == "v0.1.1" and ios["bundle_identifier"] == "org.acme.nat" and ios["debug_api_port"] == 4100 and ios["app_name"] == "nat-app"
    assert (project / "ios/App.xcodeproj/project.pbxproj").is_file() and (project / "ios/version.txt").read_text() == "0.1.1\n"
    assert "native_client" not in ios and "database" not in ios  # neither record contains the other's answers
    assert [p.name for p in out.iterdir()] == ["nat-app"]  # the staging directory is gone: renamed into place
    assert "Native iOS layer" in capsys.readouterr().out


def test_the_native_layer_adds_only_ios_and_its_answers_file(world) -> None:
    *_, out = world
    assert new(out, "layered", "--profile", "native-ios", *CHOICES) == 0
    web_only = out / "web-only"
    assert new(out, "web-only", "--profile", "native-ios", *CHOICES, "--template-ref", "v0.7.0") == 0
    layered = tree(out / "layered")
    assert {name for name in layered if name.startswith("ios/")} and IOS_ANSWERS in layered
    non_native = {name for name in layered if not name.startswith("ios/") and name != IOS_ANSWERS}
    assert non_native and all(not name.startswith("ios") for name in non_native)
    assert web_only.exists()


def test_a_failure_in_the_native_layer_leaves_nothing_at_the_destination(world, capsys) -> None:
    *_, out = world
    assert new(out, "half", "--profile", "native-ios", *CHOICES, "--native-set", "bundle_identifier=not valid") == 2
    err = capsys.readouterr().err
    assert "reverse-DNS" in err and not (out / "half").exists()
    partial = out / ".half.devkit-partial"
    assert partial.is_dir() and (partial / WEB_ANSWERS).is_file() and not (partial / IOS_ANSWERS).exists()  # kept for inspection, never deleted by devkit
    assert str(partial) in err
    assert new(out, "half", "--profile", "native-ios", *CHOICES) == 1  # a leftover is never silently reused or removed
    assert "devkit-partial" in capsys.readouterr().err and not (out / "half").exists()


def test_a_dry_run_writes_nothing_for_either_layer(world, capsys) -> None:
    *_, out = world
    assert new(out, "dry", "--profile", "native-ios", *CHOICES, "--dry-run") == 0
    assert list(out.iterdir()) == [] and "Dry run complete" in capsys.readouterr().out


def test_native_options_belong_to_the_native_profile_only(world, capsys) -> None:
    *_, out = world
    assert new(out, "x", "--native-set", "bundle_identifier=org.acme.x") == 2
    assert "no native layer" in capsys.readouterr().err and list(out.iterdir()) == []
    assert new(out, "y", "--profile", "native-ios", *CHOICES, "--native-set", "nonsense=1") == 2
    assert "Unknown option" in capsys.readouterr().err and list(out.iterdir()) == []
    assert new(out, "z", "--profile", "native-ios", *CHOICES, "--native-set", "debug_api_port=abc") == 2
    assert list(out.iterdir()) == []


def test_a_pair_of_releases_that_do_not_belong_together_is_refused_before_anything_is_written(world, capsys) -> None:
    *_, out = world
    assert new(out, "old-web", "--profile", "native-ios", *CHOICES, "--template-ref", "v0.6.1") == 2  # native_client needs web 0.7.0
    assert "needs template v0.7.0" in capsys.readouterr().err
    assert list(out.iterdir()) == []


# ------------------------------------------------------------------ status


def test_status_shows_both_layers_and_what_is_newer(world, capsys) -> None:
    *_, out = world
    assert new(out, "st", "--profile", "native-ios", *CHOICES, "--native-template-ref", "v0.1.0") == 0
    capsys.readouterr()
    assert cli.main(["status", str(out / "st")]) == 0
    captured = capsys.readouterr()
    assert "web" in captured.out and "v0.7.1" in captured.out and "native" in captured.out and "v0.1.0" in captured.out and "newer available: v0.1.1" in captured.out
    assert "NOT fully upgraded" in captured.err


def test_status_of_a_web_only_project_lists_one_layer(world, capsys) -> None:
    *_, out = world
    assert new(out, "w", "--profile", "web-core") == 0
    capsys.readouterr()
    assert cli.main(["status", str(out / "w")]) == 0 and capsys.readouterr().out.count("\n") == 1


def test_status_flags_a_pair_that_does_not_belong_together(world, capsys) -> None:
    *_, out = world
    assert new(out, "p", "--profile", "native-ios", *CHOICES) == 0
    project = out / "p"
    path = project / WEB_ANSWERS
    path.write_text(path.read_text().replace("_commit: v0.7.1", "_commit: v0.6.1"))
    assert pair_problem(layer_statuses(project)) is not None
    capsys.readouterr()
    assert cli.main(["status", str(project)]) == 1 and "may not match the server" in capsys.readouterr().err


# ------------------------------------------------------------------ layered upgrades


def project_with_both(world, name: str = "up", native_ref: str = "v0.1.0") -> Path:
    *_, out = world
    assert new(out, name, "--profile", "native-ios", *CHOICES, "--template-ref", "v0.7.0", "--native-template-ref", native_ref) == 0
    project = out / name
    (project / "notes.txt").write_text("my own file\n")
    commit(project, "initial")
    return project


def test_a_project_with_two_layers_refuses_to_guess_which_one_to_upgrade(world, capsys) -> None:
    project = project_with_both(world)
    before = tree(project)
    assert cli.main(["upgrade", str(project)]) == 2
    assert "Choose one" in capsys.readouterr().err and tree(project) == before


def test_the_native_layer_upgrades_alone_and_leaves_every_web_file_and_the_web_record_untouched(world, capsys) -> None:
    project = project_with_both(world)
    web_before = {k: v for k, v in tree(project).items() if not k.startswith("ios/") and k != IOS_ANSWERS}
    (project / "ios/MyView.swift").write_text("mine\n")
    commit(project, "my native work")
    assert cli.main(["upgrade", str(project), "--layer", "native"]) == 0
    assert answers(project, IOS_ANSWERS)["_commit"] == "v0.1.1" and (project / "ios/version.txt").read_text() == "0.1.1\n"
    assert (project / "ios/MyView.swift").read_text() == "mine\n"
    after = {k: v for k, v in tree(project).items() if not k.startswith("ios/") and k != IOS_ANSWERS}
    assert after == web_before and answers(project)["_commit"] == "v0.7.0"
    assert "Upgraded the native layer to v0.1.1" in capsys.readouterr().out


def test_the_web_layer_upgrades_alone_and_reports_that_the_project_is_not_fully_upgraded(world, capsys) -> None:
    project = project_with_both(world)
    assert cli.main(["upgrade", str(project), "--layer", "web"]) == 0
    captured = capsys.readouterr()
    assert answers(project)["_commit"] == "v0.7.1" and answers(project, IOS_ANSWERS)["_commit"] == "v0.1.0"
    assert "NOT fully upgraded: native layer: v0.1.0 -> v0.1.1 available" in captured.err


def test_a_web_upgrade_that_would_break_the_native_clients_contract_is_refused(world, point_layers_at, capsys) -> None:
    project = project_with_both(world)
    web, *_ = world
    point_layers_at(str(world[1]), str(world[3]), web_versions=((0, 1, 0), (0, 9, 0)))
    release(web, "v0.8.0")
    run_git(web, "push", "-q", str(world[1]), "main", "v0.8.0")
    before = tree(project)
    assert cli.main(["upgrade", str(project), "--layer", "web", "--to", "v0.8.0"]) == 2
    err = capsys.readouterr().err
    assert "native layer" in err and "API client" in err and tree(project) == before


def test_a_native_upgrade_needs_a_compatible_web_layer(world, capsys) -> None:
    project = project_with_both(world)
    path = project / WEB_ANSWERS
    path.write_text(path.read_text().replace("_commit: v0.7.0", "_commit: v0.6.1"))
    commit(project, "web at 0.6.1")
    assert cli.main(["upgrade", str(project), "--layer", "native"]) == 2
    assert "Upgrade the web layer first" in capsys.readouterr().err


def test_a_conflict_in_one_layer_is_reported_and_the_other_layer_is_not_touched(world, capsys) -> None:
    project = project_with_both(world)
    (project / "ios/version.txt").write_text("my own version\n")
    commit(project, "I changed a file the template also changes")
    web_before = {k: v for k, v in tree(project).items() if not k.startswith("ios/") and k != IOS_ANSWERS}
    assert cli.main(["upgrade", str(project), "--layer", "native"]) == 3
    assert "<<<<<<<" in (project / "ios/version.txt").read_text() and "merge conflicts" in capsys.readouterr().err
    assert {k: v for k, v in tree(project).items() if not k.startswith("ios/") and k != IOS_ANSWERS} == web_before


def test_each_layer_upgrade_needs_a_clean_tree_so_one_cannot_hide_inside_the_other(world, capsys) -> None:
    project = project_with_both(world)
    assert cli.main(["upgrade", str(project), "--layer", "web"]) == 0  # leaves the web changes uncommitted, as designed
    capsys.readouterr()
    assert cli.main(["upgrade", str(project), "--layer", "native"]) == 1
    assert "uncommitted changes" in capsys.readouterr().err
    assert answers(project, IOS_ANSWERS)["_commit"] == "v0.1.0"  # still honest: not upgraded
    commit(project, "chore: update web template")
    assert cli.main(["upgrade", str(project), "--layer", "native"]) == 0
    assert answers(project, IOS_ANSWERS)["_commit"] == "v0.1.1"


def test_dry_run_plans_a_layer_without_touching_anything(world, capsys) -> None:
    project = project_with_both(world)
    before = tree(project)
    assert cli.main(["upgrade", str(project), "--layer", "native", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "v0.1.0 -> v0.1.1" in out and "Dry run complete" in out and tree(project) == before


def test_a_web_only_project_still_upgrades_without_a_layer_option(world, capsys) -> None:
    *_, out = world
    assert new(out, "plain", "--profile", "web-core", "--template-ref", "v0.7.0") == 0
    commit(out / "plain")
    assert cli.main(["upgrade", str(out / "plain")]) == 0 and answers(out / "plain")["_commit"] == "v0.7.1"
    assert cli.main(["upgrade", str(out / "plain"), "--layer", "native"]) == 2


def test_the_native_layer_is_not_a_place_to_change_web_options(world, capsys) -> None:
    project = project_with_both(world)
    assert cli.main(["upgrade", str(project), "--layer", "native", "--set", "auth=false"]) == 2
    assert "Unknown option" in capsys.readouterr().err


# ------------------------------------------------------------------ native add


def test_native_add_puts_the_layer_on_a_full_stack_project_and_changes_none_of_its_files(world, capsys) -> None:
    *_, out = world
    assert new(out, "fs", "--profile", "full-stack", *CHOICES) == 0
    # a full-stack project has the baseline but not native_client yet: the web part must serve native clients first
    project = out / "fs"
    commit(project, "initial")
    assert cli.main(["native", "add", str(project)]) == 2
    assert "native_client=true" in capsys.readouterr().err and not (project / "ios").exists()
    assert cli.main(["upgrade", str(project), "--set", "native_client=true"]) == 0
    commit(project, "chore: native_client")
    before = {k: v for k, v in tree(project).items()}
    assert cli.main(["native", "add", str(project), "--native-set", "bundle_identifier=org.acme.fs"]) == 0
    after = tree(project)
    assert {k: v for k, v in after.items() if k in before} == before  # no existing file changed
    assert set(after) - set(before) >= {IOS_ANSWERS, "ios/App.xcodeproj/project.pbxproj"} and all(k == IOS_ANSWERS or k.startswith("ios/") for k in set(after) - set(before))
    assert answers(project, IOS_ANSWERS)["bundle_identifier"] == "org.acme.fs" and answers(project, IOS_ANSWERS)["_commit"] == "v0.1.1"


def test_native_add_refuses_what_it_cannot_do_safely(world, capsys) -> None:
    *_, out = world
    assert new(out, "web", "--profile", "web-core") == 0
    commit(out / "web")
    assert cli.main(["native", "add", str(out / "web")]) == 2 and "baseline" in capsys.readouterr().err
    assert new(out, "has", "--profile", "native-ios", *CHOICES) == 0
    commit(out / "has")
    assert cli.main(["native", "add", str(out / "has")]) == 1 and "already has" in capsys.readouterr().err
    assert new(out, "dirty", "--profile", "full-stack", *CHOICES) == 0
    commit(out / "dirty")
    (out / "dirty/stray.txt").write_text("x\n")
    assert cli.main(["native", "add", str(out / "dirty")]) == 1 and "uncommitted" in capsys.readouterr().err
    assert not (out / "dirty/ios").exists()
    assert cli.main(["native", "add", str(out / "missing")]) == 1


def test_native_add_dry_run_writes_nothing(world, capsys) -> None:
    *_, out = world
    assert new(out, "base", "--profile", "full-stack", *CHOICES) == 0
    commit(out / "base", "initial")
    assert cli.main(["upgrade", str(out / "base"), "--set", "native_client=true"]) == 0
    commit(out / "base")
    before = tree(out / "base")
    assert cli.main(["native", "add", str(out / "base"), "--dry-run"]) == 0
    assert tree(out / "base") == before and "Dry run complete" in capsys.readouterr().out
