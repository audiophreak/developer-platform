from __future__ import annotations

import dataclasses

import pytest

from devkit.errors import UsageError
from devkit.profiles import PROFILES
from devkit.sources import ResolvedTemplate
from devkit.validation import ensure_options_available, parse_options, validate_destination_name

SPEC = PROFILES["web-core"].template


@pytest.mark.parametrize("name", ["demo", "my-app", "a1", "App.2_x", "9lives", "a" * 100])
def test_safe_path_segments_are_accepted(name: str) -> None:
    assert validate_destination_name(name) == name


@pytest.mark.parametrize(
    "name",
    ["", ".", "..", "../escape", "a/b", "/abs", "-flag", ".hidden", "a b", "a\nb", "~", "a" * 101, "ünï"],
)
def test_names_that_are_not_a_single_safe_path_segment_are_rejected(name: str) -> None:
    with pytest.raises(UsageError):
        validate_destination_name(name)


def test_options_are_parsed_and_typed() -> None:
    assert parse_options(SPEC, ["zod=true", "cache_components=false"]) == {"zod": True, "cache_components": False}
    assert parse_options(SPEC, ["cache_components=false"]) == {"cache_components": False}
    assert parse_options(SPEC, ["cache_components=TRUE"]) == {"cache_components": True}
    assert parse_options(SPEC, []) == {}


@pytest.mark.parametrize(
    ("pair", "message"),
    [
        ("nonsense", "NAME=VALUE"),
        ("=true", "NAME=VALUE"),
        ("unknown=1", "Unknown option"),
        ("app_name=x", "cannot change"),
        ("app_description=x", "cannot change"),
        ("cache_components=maybe", "true/false"),
    ],
)
def test_bad_options_are_rejected(pair: str, message: str) -> None:
    with pytest.raises(UsageError, match=message):
        parse_options(SPEC, [pair])


def test_duplicate_options_are_rejected() -> None:
    with pytest.raises(UsageError, match="more than once"):
        parse_options(SPEC, ["cache_components=true", "cache_components=false"])


def test_string_options_are_passed_through() -> None:
    from devkit.profiles import Option

    spec = dataclasses.replace(SPEC, options=(Option("greeting", "str", "hi"),))
    assert parse_options(spec, ["greeting=hello world=1"]) == {"greeting": "hello world=1"}


# ---------------------------------------------------------------- options versus the selected release


def published(ref: str) -> ResolvedTemplate:
    return ResolvedTemplate(location="https://example.invalid/t.git", ref=ref, mode="published", local_root=None)


def test_an_option_newer_than_the_release_is_refused() -> None:
    with pytest.raises(UsageError, match="'zod' needs template v0.2.0 or newer, but release v0.1.5 is selected"):
        ensure_options_available(SPEC, {"zod": True}, published("v0.1.5"))


def test_options_the_release_has_are_accepted() -> None:
    ensure_options_available(SPEC, {"zod": False}, published("v0.2.0"))
    ensure_options_available(SPEC, {"zod": True, "cache_components": False}, published("v0.3.0"))
    ensure_options_available(SPEC, {"cache_components": False}, published("v0.1.0"))


def test_no_options_means_no_check_even_for_an_old_release() -> None:
    ensure_options_available(SPEC, {}, published("v0.1.0"))


def test_a_local_checkout_is_judged_by_its_own_copier_yml(tmp_path) -> None:
    count = iter(range(100))

    def local(copier_yml: str | None) -> ResolvedTemplate:
        root = tmp_path / f"checkout-{next(count)}"
        root.mkdir()
        if copier_yml is not None:
            (root / "copier.yml").write_text(copier_yml)
        return ResolvedTemplate(location=str(root), ref="HEAD", mode="local", local_root=root)

    ensure_options_available(SPEC, {"zod": True}, local("app_name:\n  type: str\nzod:\n  type: yaml\n"))
    with pytest.raises(UsageError, match="not a question of the template at HEAD"):
        ensure_options_available(SPEC, {"zod": True}, local("app_name:\n  type: str\n"))
    # unreadable: not guessed at here (the after-generation check still catches an ignored option)
    ensure_options_available(SPEC, {"zod": True}, local(None))
