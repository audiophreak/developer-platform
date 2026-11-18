"""Offline compatibility contract: the profile registry versus a snapshot of every supported release.

No network, no checkout of the template, no credentials, so this runs in CI. The snapshots are
captured from release tags by tools/capture_contract.py; the live drift test in
test_integration_web_core.py (the release gate) proves they still match the real template.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devkit.profiles import get_profile

CONTRACTS = Path(__file__).resolve().parent / "contracts" / "web-core"
SPEC = get_profile("web-core").template
STRICT_FROM = (0, 2, 0)  # first release whose boolean questions are strict (yaml + choices)


def version_of(path: Path) -> tuple[int, int, int]:
    major, minor, patch = path.stem.split(".")
    return int(major), int(minor), int(patch)


SNAPSHOTS = sorted(CONTRACTS.glob("*.json"), key=version_of)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def boolean_form_is_valid(question: dict, version: tuple[int, int, int]) -> bool:
    if version >= STRICT_FROM:
        return question.get("type") == "yaml" and question.get("choices") == [False, True]
    return question.get("type") == "bool"


def test_snapshots_exist_and_are_named_for_their_release() -> None:
    assert SNAPSHOTS, "no contract snapshots (run tools/capture_contract.py)"
    for path in SNAPSHOTS:
        assert load(path)["release"] == "v" + path.stem


def test_every_supported_boundary_has_a_snapshot() -> None:
    """The oldest supported release, and the release that introduced each option, are all covered."""
    covered = {version_of(p) for p in SNAPSHOTS}
    needed = {SPEC.versions.minimum} | {o.since for o in SPEC.options if o.since >= SPEC.versions.minimum}
    assert needed <= covered, f"missing snapshots for {sorted(needed - covered)}"


def test_snapshots_do_not_claim_releases_outside_the_supported_range() -> None:
    for path in SNAPSHOTS:
        assert SPEC.versions.contains(version_of(path)), f"{path.name} is outside {SPEC.versions}"


@pytest.mark.parametrize("snapshot", SNAPSHOTS, ids=lambda p: "v" + p.stem)
def test_the_registry_matches_each_supported_release(snapshot: Path) -> None:
    version, data = version_of(snapshot), load(snapshot)
    questions = data["questions"]

    # always sent by devkit
    assert questions["app_name"]["type"] == "str"
    assert questions["app_description"]["type"] == "str"
    assert data["node_major"] == SPEC.node_major

    for option in SPEC.options:
        if option.since > version:
            assert option.name not in questions, f"{option.name} exists before its declared `since`"
            continue
        assert option.name in questions, f"{option.name} is declared since v{'.'.join(map(str, option.since))}"
        question = questions[option.name]
        assert question["default"] == option.default, f"{option.name}: default differs"
        if option.kind == "bool":
            assert boolean_form_is_valid(question, version), f"{option.name}: unexpected boolean form {question}"
        if option.choices:
            assert question["type"] == "str" and question["choices"] == list(option.choices), f"{option.name}: the choices differ from the registry's"


def test_every_question_devkit_does_not_know_is_computed_or_unneeded() -> None:
    """A new template question with no default would make `devkit new` fail; make that visible."""
    known = {"app_name", "app_description"} | {o.name for o in SPEC.options}
    for path in SNAPSHOTS:
        for name, question in load(path)["questions"].items():
            if name in known or question.get("computed"):
                continue
            assert "default" in question, f"{path.name}: question {name!r} has no default and devkit never sets it"
