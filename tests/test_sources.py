from __future__ import annotations

from pathlib import Path

import pytest

from conftest import make_template_repo, run_git
from devkit.errors import TemplateUnavailableError, UsageError
from devkit.profiles import PROFILES, VersionRange
from devkit.sources import (
    SourceInfo,
    format_tag,
    inspect_checkout,
    list_release_tags,
    parse_release_tag,
    recordable_path,
    resolve_template,
)

SPEC = PROFILES["web-core"].template
RANGE = VersionRange((0, 1, 0), (0, 2, 0))


@pytest.mark.parametrize(
    ("tag", "expected"),
    [("v0.1.0", (0, 1, 0)), ("v12.34.56", (12, 34, 56)), ("v0.10.2", (0, 10, 2))],
)
def test_release_tags_parse(tag: str, expected: tuple) -> None:
    assert parse_release_tag(tag) == expected
    assert format_tag(expected) == tag


@pytest.mark.parametrize(
    "tag", ["0.1.0", "v0.1", "v0.1.0-rc.1", "v0.1.0rc1", "latest", "v0.1.0.1", "V0.1.0", ""]
)
def test_other_tags_are_not_releases(tag: str) -> None:
    assert parse_release_tag(tag) is None


@pytest.fixture()
def tagged_repo(tmp_path: Path) -> Path:
    repo = make_template_repo(tmp_path / "tpl", ("v0.1.0", "v0.1.1", "v0.2.0", "v1.0.0"))
    for odd in ("v0.3.0-rc.1", "latest", "0.1.5"):
        run_git(repo, "tag", odd)
    return repo


def test_only_release_tags_are_listed_oldest_first(tagged_repo: Path) -> None:
    assert list_release_tags(str(tagged_repo)) == [(0, 1, 0), (0, 1, 1), (0, 2, 0), (1, 0, 0)]


def test_annotated_release_tags_are_listed_once(tmp_path: Path) -> None:
    repo = make_template_repo(tmp_path / "tpl")
    run_git(repo, "tag", "-a", "v0.1.0", "-m", "annotated release")
    run_git(repo, "tag", "v0.1.1")  # lightweight
    assert list_release_tags(str(repo)) == [(0, 1, 0), (0, 1, 1)]


def test_unreachable_source_is_reported_without_leaking_credentials() -> None:
    url = "https://someone:hunter2-token@localhost:9/none.git"
    with pytest.raises(TemplateUnavailableError) as raised:
        list_release_tags(url)
    message = str(raised.value)
    assert "unavailable" in message and "hunter2-token" not in message


def test_missing_local_source_is_unavailable(tmp_path: Path) -> None:
    with pytest.raises(TemplateUnavailableError, match="unavailable"):
        list_release_tags(str(tmp_path / "nope.git"))


def test_unavailable_message_explains_private_repository_access(tmp_path: Path) -> None:
    with pytest.raises(TemplateUnavailableError) as raised:
        list_release_tags(str(tmp_path / "nope.git"))
    message = str(raised.value)
    assert "private" in message and "authenticate without prompting" in message
    assert "docs/publishing.md" in message and "--template" in message


# ---------------------------------------------------------------- published mode


def _spec(url: str):
    import dataclasses

    return dataclasses.replace(SPEC, url=url, versions=RANGE)


def test_published_mode_picks_the_newest_supported_release(tagged_repo: Path) -> None:
    resolved = resolve_template(_spec(str(tagged_repo)))
    assert (resolved.mode, resolved.ref, resolved.location) == ("published", "v0.1.1", str(tagged_repo))
    assert resolved.local_root is None


def test_published_mode_honours_an_explicit_supported_tag(tagged_repo: Path) -> None:
    assert resolve_template(_spec(str(tagged_repo)), template_ref="v0.1.0").ref == "v0.1.0"


def test_a_release_outside_the_supported_range_is_refused(tagged_repo: Path) -> None:
    with pytest.raises(UsageError, match="outside the range"):
        resolve_template(_spec(str(tagged_repo)), template_ref="v0.2.0")
    with pytest.raises(UsageError, match="outside the range"):
        resolve_template(_spec(str(tagged_repo)), template_ref="v1.0.0")


@pytest.mark.parametrize("ref", ["main", "HEAD", "abc1234", "v0.1.0-rc.1"])
def test_published_mode_only_accepts_release_tags(tagged_repo: Path, ref: str) -> None:
    with pytest.raises(UsageError, match="not a release tag"):
        resolve_template(_spec(str(tagged_repo)), template_ref=ref)


def test_a_supported_tag_that_does_not_exist_is_unavailable(tagged_repo: Path) -> None:
    with pytest.raises(TemplateUnavailableError, match="does not exist"):
        resolve_template(_spec(str(tagged_repo)), template_ref="v0.1.9")


def test_no_supported_release_is_unavailable(tmp_path: Path) -> None:
    only_future = make_template_repo(tmp_path / "future", ("v1.0.0",))
    with pytest.raises(TemplateUnavailableError, match="first release been tagged"):
        resolve_template(_spec(str(only_future)))
    untagged = make_template_repo(tmp_path / "untagged")
    with pytest.raises(TemplateUnavailableError, match="No supported template release"):
        resolve_template(_spec(str(untagged)))


def test_a_template_url_override_still_resolves_a_release(tagged_repo: Path, tmp_path: Path) -> None:
    bare = tmp_path / "remote.git"
    run_git(tmp_path, "clone", "-q", "--bare", str(tagged_repo), str(bare))
    resolved = resolve_template(SPEC, template=str(bare))
    assert (resolved.mode, resolved.ref, resolved.location) == ("published", "v0.1.1", str(bare))


# ---------------------------------------------------------------- local mode


def test_local_mode_renders_the_checkout_as_it_is(tagged_repo: Path) -> None:
    (tagged_repo / "template" / "version.txt").write_text("dirty\n")
    resolved = resolve_template(SPEC, template=str(tagged_repo))
    assert (resolved.mode, resolved.ref, resolved.local_root) == ("local", "HEAD", tagged_repo.resolve())
    assert any("uncommitted changes" in note for note in resolved.warnings)
    assert any("Local template mode" in note for note in resolved.warnings)


def test_local_mode_with_an_explicit_ref_uses_it(tagged_repo: Path) -> None:
    resolved = resolve_template(SPEC, template=str(tagged_repo), template_ref="v0.2.0")
    assert resolved.ref == "v0.2.0" and resolved.mode == "local"
    assert not any("uncommitted" in note for note in resolved.warnings)


def test_local_mode_without_commits_lets_copier_decide(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    (repo / "copier.yml").write_text("{}\n")
    run_git(repo, "init", "-q", "-b", "main")
    resolved = resolve_template(SPEC, template=str(repo))
    assert resolved.ref is None
    assert any("no commits" in note for note in resolved.warnings)


def test_local_directory_must_be_a_copier_template(tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="no copier.yml"):
        resolve_template(SPEC, template=str(tmp_path))


def test_local_ref_needs_a_git_repository(tmp_path: Path) -> None:
    (tmp_path / "copier.yml").write_text("{}\n")
    with pytest.raises(UsageError, match="needs a git repository"):
        resolve_template(SPEC, template=str(tmp_path), template_ref="v0.1.0")


def test_inspect_checkout(tmp_path: Path, tagged_repo: Path) -> None:
    assert inspect_checkout(tagged_repo) == SourceInfo(True, True, False)
    (tagged_repo / "x").write_text("x")
    assert inspect_checkout(tagged_repo).dirty is True
    assert inspect_checkout(tmp_path) == SourceInfo(False, False, False)


def test_recordable_path_is_home_relative_for_git_checkouts(tmp_path: Path) -> None:
    home = tmp_path / "home"
    checkout = home / "src" / "web-core-template"
    checkout.mkdir(parents=True)
    git = SourceInfo(is_git_root=True, has_commits=True, dirty=False)
    assert recordable_path(checkout, git, home=home) == "~/src/web-core-template"
    outside = tmp_path / "elsewhere" / "tpl"
    outside.mkdir(parents=True)
    assert recordable_path(outside, git, home=home) == str(outside.resolve())
    not_git = SourceInfo(is_git_root=False, has_commits=False, dirty=False)
    assert recordable_path(checkout, not_git, home=home) == str(checkout.resolve())
