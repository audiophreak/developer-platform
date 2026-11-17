from __future__ import annotations

import dataclasses

import pytest

from devkit.errors import UsageError
from devkit.profiles import PROFILES
from devkit.validation import parse_options, validate_destination_name

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
