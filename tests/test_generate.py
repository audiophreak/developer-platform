from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import HTTPS_ORIGIN, PLATFORM_ROOT, make_remote, make_template_repo, publish, release, run_git
from devkit.errors import OperationError, TemplateUnavailableError, UsageError
from devkit.generate import NewRequest, generate_project


def _entries(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


def _answers(project: Path) -> dict:
    return yaml.safe_load((project / ".copier-answers.yml").read_text())


def _version(project: Path) -> str:
    return (project / "version.txt").read_text().strip()


@pytest.fixture()
def published(tmp_path, point_profile_at, https_origin):
    """A 'published' template: releases v0.1.0, v0.1.1, v0.2.0, served at an https-style URL."""
    repo = make_template_repo(tmp_path / "work" / "web-core-template", ("v0.1.0", "v0.1.1", "v0.2.0"))
    remote = make_remote(repo, tmp_path / "remote" / "web-core-template.git")
    url = https_origin(remote)
    point_profile_at(url)
    out = tmp_path / "out"
    out.mkdir()
    return repo, remote, url, out


# ------------------------------------------------------------ published mode


def test_published_mode_renders_the_newest_supported_release(published) -> None:
    _, _, url, out = published
    result = generate_project(NewRequest("pub-app", "Published app", out))
    project = result.destination
    assert (result.template.mode, result.template.ref) == ("published", "v0.1.1")
    assert _version(project) == "0.1.1"  # not v0.2.0: outside the supported range
    assert "# pub-app" in (project / "README.md").read_text()


def test_published_mode_records_a_portable_git_origin(published) -> None:
    _, remote, url, out = published
    project = generate_project(NewRequest("pub-app", output_dir=out)).destination
    answers = _answers(project)
    assert answers["_src_path"] == HTTPS_ORIGIN == url
    assert answers["_commit"] == "v0.1.1"
    text = (project / ".copier-answers.yml").read_text()
    assert str(remote) not in text and str(Path.home()) not in text and "/Users/" not in text


def test_an_explicit_supported_release_is_rendered(published) -> None:
    _, _, _, out = published
    result = generate_project(NewRequest("pinned-app", output_dir=out, template_ref="v0.1.0"))
    assert _version(result.destination) == "0.1.0"
    assert _answers(result.destination)["_commit"] == "v0.1.0"


def test_template_defaults_apply_when_nothing_is_given(published) -> None:
    _, _, _, out = published
    project = generate_project(NewRequest("default-app", output_dir=out)).destination
    assert "Mini default description" in (project / "README.md").read_text()
    assert (project / "flags.txt").read_text().strip() == "cache_components=true"


def test_options_reach_the_template(published) -> None:
    _, _, _, out = published
    project = generate_project(
        NewRequest("opt-app", output_dir=out, options=("cache_components=false",))
    ).destination
    assert (project / "flags.txt").read_text().strip() == "cache_components=false"
    assert _answers(project)["cache_components"] is False


def test_unknown_options_are_rejected_before_anything_is_written(published) -> None:
    _, _, _, out = published
    with pytest.raises(UsageError, match="Unknown option"):
        generate_project(NewRequest("opt-app", output_dir=out, options=("bogus=1",)))
    assert _entries(out) == []


def test_the_templates_own_validation_rejects_a_bad_name_with_exit_2(published) -> None:
    _, _, _, out = published
    with pytest.raises(UsageError, match="Validation error for question 'app_name'") as raised:
        generate_project(NewRequest("Bad", output_dir=out))
    assert raised.value.exit_code == 2
    assert _entries(out) == []


def test_dry_run_writes_nothing_and_reports_the_template(published) -> None:
    _, _, _, out = published
    seen = []
    result = generate_project(
        NewRequest("dry-app", output_dir=out, dry_run=True), on_resolved=seen.append
    )
    assert result.dry_run and not result.destination.exists()
    assert _entries(out) == []
    assert [(t.mode, t.ref) for t in seen] == [("published", "v0.1.1")]


def test_unavailable_published_template_fails_cleanly(tmp_path: Path, point_profile_at) -> None:
    point_profile_at(str(tmp_path / "never-published.git"))
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(TemplateUnavailableError, match="unavailable") as raised:
        generate_project(NewRequest("app", output_dir=out))
    assert raised.value.exit_code == 1
    assert _entries(out) == []


def test_a_published_template_without_a_supported_release_fails_cleanly(
    tmp_path: Path, point_profile_at
) -> None:
    repo = make_template_repo(tmp_path / "tpl")  # commits but no tags yet
    point_profile_at(str(repo))
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(TemplateUnavailableError, match="No supported template release"):
        generate_project(NewRequest("app", output_dir=out))
    assert _entries(out) == []


def test_failed_generation_is_reported_and_leaves_nothing_behind(
    tmp_path: Path, point_profile_at
) -> None:
    repo = make_template_repo(tmp_path / "tpl", ("v0.1.0",))
    release(repo, "v0.1.1", **{"broken.txt.jinja": "{% endfor %}"})  # template syntax error
    point_profile_at(str(repo))
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(OperationError, match="failed") as raised:
        generate_project(NewRequest("fail-app", output_dir=out))
    assert raised.value.exit_code == 1
    assert _entries(out) == []


# ------------------------------------------------------------ local mode


def test_local_mode_renders_unreleased_work_and_records_a_local_path(tmp_path: Path) -> None:
    repo = make_template_repo(tmp_path / "tpl", ("v0.1.0",))
    (repo / "template" / "version.txt").write_text("unreleased\n")
    run_git(repo, "commit", "-q", "-am", "work in progress")
    out = tmp_path / "out"
    out.mkdir()
    result = generate_project(NewRequest("dev-app", output_dir=out, template=str(repo)))
    assert (result.template.mode, result.template.ref) == ("local", "HEAD")
    assert _version(result.destination) == "unreleased"
    assert _answers(result.destination)["_src_path"] == str(repo.resolve())
    assert any("Local template mode" in note for note in result.warnings)


def test_local_mode_can_render_an_older_release_of_the_checkout(tmp_path: Path) -> None:
    repo = make_template_repo(tmp_path / "tpl", ("v0.1.0", "v0.2.0"))
    out = tmp_path / "out"
    out.mkdir()
    project = generate_project(
        NewRequest("old-app", output_dir=out, template=str(repo), template_ref="v0.1.0")
    ).destination
    assert _version(project) == "0.1.0"
    assert _answers(project)["_commit"] == "v0.1.0"


def test_local_mode_with_a_missing_ref_fails_cleanly(tmp_path: Path) -> None:
    repo = make_template_repo(tmp_path / "tpl", ("v0.1.0",))
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(OperationError, match="failed"):
        generate_project(NewRequest("app", output_dir=out, template=str(repo), template_ref="v9.9.9"))
    assert _entries(out) == []


def test_local_mode_refuses_a_destination_inside_the_template_checkout(tmp_path: Path) -> None:
    repo = make_template_repo(tmp_path / "tpl", ("v0.1.0",))
    with pytest.raises(OperationError, match="inside the template checkout"):
        generate_project(NewRequest("inner", output_dir=repo, template=str(repo)))
    assert not (repo / "inner").exists()


# ------------------------------------------------------------ never overwrite


def test_existing_directory_is_never_overwritten(published) -> None:
    _, _, _, out = published
    target = out / "taken"
    target.mkdir()
    (target / "keep.txt").write_text("precious")
    with pytest.raises(OperationError, match="already exists"):
        generate_project(NewRequest("taken", output_dir=out))
    assert _entries(target) == ["keep.txt"] and (target / "keep.txt").read_text() == "precious"


def test_existing_empty_directory_file_and_symlink_are_refused_too(published) -> None:
    _, _, _, out = published
    (out / "empty").mkdir()
    (out / "afile").write_text("x")
    elsewhere = out.parent / "elsewhere"
    elsewhere.mkdir()
    (out / "alink").symlink_to(elsewhere, target_is_directory=True)
    for name in ("empty", "afile", "alink"):
        with pytest.raises(OperationError, match="already exists"):
            generate_project(NewRequest(name, output_dir=out))
    assert _entries(out / "empty") == [] and _entries(elsewhere) == []


def test_missing_output_directory_is_refused(published) -> None:
    _, _, _, out = published
    with pytest.raises(OperationError, match="does not exist"):
        generate_project(NewRequest("app", output_dir=out / "nope"))
    assert not (out / "nope").exists()


def test_destination_inside_the_platform_checkout_is_refused(published) -> None:
    inside = PLATFORM_ROOT / "docs" / "should-not-exist"
    with pytest.raises(OperationError, match="inside the developer-platform"):
        generate_project(NewRequest("should-not-exist", output_dir=PLATFORM_ROOT / "docs"))
    assert not inside.exists()


@pytest.mark.parametrize("name", ["../escape", "a/b", "-x", ""])
def test_unsafe_names_are_rejected_before_touching_the_filesystem(published, name: str) -> None:
    _, _, _, out = published
    with pytest.raises(UsageError):
        generate_project(NewRequest(name, output_dir=out))
    assert _entries(out) == [] and not (out.parent / "escape").exists()


def test_reserved_profiles_are_rejected_before_touching_the_filesystem(published) -> None:
    _, _, _, out = published
    with pytest.raises(UsageError, match="reserved for a later milestone"):
        generate_project(NewRequest("app", output_dir=out, profile="native-ios"))
    assert _entries(out) == []


# ------------------------------------------------------------ upgrades of devkit-made projects


def _adopt(project: Path) -> None:
    """The user's own work, committed (Copier requires a clean git repository to update)."""
    run_git(project, "init", "-q", "-b", "main")
    (project / "notes.txt").write_text("my own file\n")
    readme = project / "README.md"
    readme.write_text(readme.read_text() + "\nLocal note.\n")
    run_git(project, "add", "-A")
    run_git(project, "commit", "-q", "-m", "initial")


def _copier_update(project: Path, *args: str):
    import os
    import subprocess
    import sys

    from conftest import GIT_TEST_ENV

    return subprocess.run(
        [sys.executable, "-m", "copier", "update", "--defaults", "--skip-answered", "--quiet", *args],
        cwd=project,
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_TEST_ENV},
        check=False,
    )


def test_a_devkit_project_upgrades_through_its_recorded_origin_to_a_pinned_release(
    published,
) -> None:
    """The recorded https origin is enough for `copier update --vcs-ref <supported tag>`."""
    repo, remote, url, out = published
    project = generate_project(NewRequest("up-app", output_dir=out, template_ref="v0.1.0")).destination
    assert _answers(project)["_src_path"] == url
    _adopt(project)

    release(repo, "v0.1.2", **{"CONTRIBUTING.md.jinja": "# Contributing to {{ app_name }}\n"})
    publish(repo, remote, "v0.1.2")

    result = _copier_update(project, "--vcs-ref", "v0.1.2")
    assert result.returncode == 0, result.stderr
    assert _version(project) == "0.1.2"
    assert (project / "CONTRIBUTING.md").read_text() == "# Contributing to up-app\n"
    assert (project / "notes.txt").read_text() == "my own file\n"
    assert "Local note." in (project / "README.md").read_text()
    answers = _answers(project)
    assert (answers["_src_path"], answers["_commit"]) == (url, "v0.1.2")


def test_a_plain_copier_update_takes_the_newest_tag_even_outside_the_supported_range(
    published,
) -> None:
    """Why docs/usage.md says to pin --vcs-ref: Copier ignores the supported range."""
    repo, remote, url, out = published  # v0.2.0 is published but outside >=0.1.0,<0.2.0
    project = generate_project(NewRequest("jump-app", output_dir=out, template_ref="v0.1.0")).destination
    _adopt(project)
    assert _copier_update(project).returncode == 0
    assert _version(project) == "0.2.0"
