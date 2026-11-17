"""devkit 0.3 supports template releases 0.1.x and 0.2.x.

The mini templates here mirror the real release history: v0.1.x has no `zod` question, v0.2.x has
it. Copier silently ignores an answer for a question that does not exist, so the dangerous case is
asking an old release for a new feature; these tests pin that it is refused, loudly and early.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
import yaml

from conftest import make_remote, make_versioned_template, run_git
from devkit import cli, profiles
from devkit.errors import OperationError, UsageError
from devkit.generate import NewRequest, generate_project


@pytest.fixture()
def versioned(tmp_path, point_profile_at, https_origin):
    """Published releases v0.1.0, v0.1.1, v0.2.0, v0.2.1; the registry supports >=0.1.0,<0.3.0."""
    repo = make_versioned_template(tmp_path / "work" / "web-core-template")
    remote = make_remote(repo, tmp_path / "remote" / "web-core-template.git")
    url = https_origin(remote)
    point_profile_at(url, versions=((0, 1, 0), (0, 3, 0)))
    out = tmp_path / "out"
    out.mkdir()
    return repo, url, out


def entries(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


def answers(project: Path) -> dict:
    return yaml.safe_load((project / ".copier-answers.yml").read_text())


def flags(project: Path) -> list[str]:
    return (project / "flags.txt").read_text().splitlines()


def test_the_default_is_the_newest_release_and_supports_the_feature(versioned) -> None:
    _, _, out = versioned
    result = generate_project(NewRequest("new-app", output_dir=out, options=("zod=true",)))
    assert result.template.ref == "v0.2.1"
    assert flags(result.destination) == ["cache_components=true", "zod=true"]
    assert answers(result.destination)["zod"] is True


@pytest.mark.parametrize("tag", ["v0.1.0", "v0.1.1", "v0.2.0", "v0.2.1"])
def test_every_supported_release_still_generates_with_no_options(versioned, tag: str) -> None:
    _, _, out = versioned
    project = generate_project(NewRequest("app", output_dir=out, template_ref=tag)).destination
    assert (project / "version.txt").read_text().strip() == tag.lstrip("v")
    assert answers(project)["_commit"] == tag


def test_an_old_release_keeps_working_with_the_options_it_has(versioned) -> None:
    _, _, out = versioned
    project = generate_project(
        NewRequest("old-app", output_dir=out, template_ref="v0.1.1", options=("cache_components=false",))
    ).destination
    assert flags(project) == ["cache_components=false"]  # v0.1.x has no zod line
    assert "zod" not in answers(project)


@pytest.mark.parametrize("tag", ["v0.1.0", "v0.1.1"])
def test_a_feature_an_old_release_lacks_is_refused_not_silently_dropped(versioned, tag: str) -> None:
    _, _, out = versioned
    with pytest.raises(UsageError, match=rf"'zod' needs template v0\.2\.0 or newer, but release {tag}") as raised:
        generate_project(NewRequest("app", output_dir=out, template_ref=tag, options=("zod=true",)))
    assert raised.value.exit_code == 2
    assert entries(out) == []


def test_the_refusal_applies_to_dry_runs_too(versioned) -> None:
    _, _, out = versioned
    with pytest.raises(UsageError, match="needs template v0.2.0"):
        generate_project(NewRequest("app", output_dir=out, template_ref="v0.1.0", options=("zod=false",), dry_run=True))
    assert entries(out) == []


def test_the_first_release_that_has_the_feature_accepts_it(versioned) -> None:
    _, _, out = versioned
    project = generate_project(
        NewRequest("edge-app", output_dir=out, template_ref="v0.2.0", options=("zod=true",))
    ).destination
    assert answers(project)["zod"] is True


def test_the_refusal_is_exit_code_2_through_the_command_line(versioned, capsys) -> None:
    _, _, out = versioned
    code = cli.main(["new", "app", "--template-ref", "v0.1.0", "--set", "zod=true", "--output-dir", str(out)])
    assert code == 2
    assert "needs template v0.2.0" in capsys.readouterr().err
    assert entries(out) == []


# ------------------------------------------------------------------ local checkouts


def test_a_local_checkout_at_head_is_judged_by_its_own_questions(versioned, tmp_path: Path) -> None:
    repo, _, out = versioned
    project = generate_project(NewRequest("local-app", output_dir=out, template=str(repo), options=("zod=true",))).destination
    assert answers(project)["zod"] is True


def test_a_local_release_ref_is_judged_by_the_registry(versioned) -> None:
    repo, _, out = versioned
    with pytest.raises(UsageError, match="needs template v0.2.0"):
        generate_project(NewRequest("app", output_dir=out, template=str(repo), template_ref="v0.1.0", options=("zod=true",)))
    assert entries(out) == []


def test_a_local_branch_is_judged_by_the_questions_in_its_copier_yml(versioned) -> None:
    repo, _, out = versioned
    run_git(repo, "branch", "legacy", "v0.1.0")  # a ref that is not a release tag
    with pytest.raises(UsageError, match="not a question of the template at legacy"):
        generate_project(NewRequest("app", output_dir=out, template=str(repo), template_ref="legacy", options=("zod=true",)))
    assert entries(out) == []
    # ...and the same branch works for an option it does have
    project = generate_project(
        NewRequest("ok-app", output_dir=out, template=str(repo), template_ref="legacy", options=("cache_components=false",))
    ).destination
    assert flags(project) == ["cache_components=false"]


# ------------------------------------------------------------------ defence in depth


def test_an_option_the_template_ignores_is_caught_after_generation(versioned, monkeypatch) -> None:
    """If the registry were wrong about a release, Copier would drop the answer; devkit must notice."""
    _, _, out = versioned
    profile = profiles.PROFILES["web-core"]
    wrong = tuple(dataclasses.replace(o, since=(0, 1, 0)) if o.name == "zod" else o for o in profile.template.options)
    monkeypatch.setitem(
        profiles.PROFILES, "web-core",
        dataclasses.replace(profile, template=dataclasses.replace(profile.template, options=wrong)),
    )  # fmt: skip
    with pytest.raises(OperationError, match="'zod' was not recorded") as raised:
        generate_project(NewRequest("app", output_dir=out, template_ref="v0.1.0", options=("zod=true",)))
    assert raised.value.exit_code == 1
    assert "Inspect" in str(raised.value)
    assert (out / "app").is_dir()  # left in place for inspection, never deleted
