"""Contract between this platform and the real web-core-template.

Needs a checkout of the template: `../web-core-template` next to this repository, or the path
in $WEB_CORE_TEMPLATE. Skipped when neither exists. This is the guard against the two
repositories drifting apart: the profile registry here must match what the template offers.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import PLATFORM_ROOT
from devkit.errors import UsageError
from devkit.generate import NewRequest, generate_project
from devkit.profiles import PROFILES
from devkit.sources import list_release_tags

pytestmark = pytest.mark.integration

TEMPLATE_DIR = Path(os.environ.get("WEB_CORE_TEMPLATE", PLATFORM_ROOT.parent / "web-core-template"))
SPEC = PROFILES["web-core"].template


@pytest.fixture(scope="module")
def questions() -> dict:
    if not (TEMPLATE_DIR / "copier.yml").is_file():
        pytest.skip(f"no web-core-template checkout at {TEMPLATE_DIR}")
    config = yaml.safe_load((TEMPLATE_DIR / "copier.yml").read_text())
    return {k: v for k, v in config.items() if not k.startswith("_")}


def test_template_accepts_the_answers_the_cli_always_sends(questions: dict) -> None:
    assert {"app_name", "app_description"} <= set(questions)


def test_every_registry_option_is_a_template_question_of_the_same_kind(questions: dict) -> None:
    for option in SPEC.options:
        assert option.name in questions, f"{option.name} is not a template question"
        question = questions[option.name]
        boolean = question["type"] == "bool" or (question["type"] == "yaml" and question.get("choices") == [False, True])
        assert boolean if option.kind == "bool" else question["type"] == option.kind


def test_registry_node_major_matches_the_template_pin(questions: dict) -> None:
    nvmrc = (TEMPLATE_DIR / "template" / ".nvmrc").read_text().strip()
    assert int(nvmrc.split(".")[0]) == SPEC.node_major


def test_every_registry_default_matches_the_template_default(questions: dict) -> None:
    for option in SPEC.options:
        assert questions[option.name]["default"] == option.default, option.name


def _checkout_is_at_a_release() -> bool:
    result = subprocess.run(
        ["git", "-C", str(TEMPLATE_DIR), "describe", "--exact-match", "--tags", "HEAD"],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    return result.returncode == 0 and not subprocess.run(
        ["git", "-C", str(TEMPLATE_DIR), "status", "--porcelain"], capture_output=True, text=True, check=False
    ).stdout.strip()


def test_published_releases_are_not_older_than_the_supported_range(questions: dict) -> None:
    """The registry must not claim support for template releases that do not exist."""
    if not _checkout_is_at_a_release():
        pytest.skip("the template checkout has unreleased work; this applies once it is tagged")
    tags = list_release_tags(str(TEMPLATE_DIR))
    assert tags and max(tags) >= SPEC.versions.minimum, "the registry supports releases that do not exist"


def test_local_mode_generates_the_real_template(questions: dict, tmp_path: Path) -> None:
    result = generate_project(
        NewRequest(
            "contract-app",
            "Contract test application",
            tmp_path,
            template=str(TEMPLATE_DIR),
            options=("cache_components=false",),
        )
    )
    project = result.destination
    assert (project / "package.json").is_file() and (project / "next.config.ts").is_file()
    assert "cacheComponents" not in (project / "next.config.ts").read_text()
    answers = yaml.safe_load((project / ".copier-answers.yml").read_text())
    assert answers["app_name"] == "contract-app" and answers["cache_components"] is False


def test_local_mode_selects_the_zod_feature_in_the_real_template(questions: dict, tmp_path: Path) -> None:
    import json

    enabled = generate_project(
        NewRequest("zod-contract", "Zod contract test", tmp_path, template=str(TEMPLATE_DIR), options=("zod=true",))
    ).destination
    assert json.loads((enabled / "package.json").read_text())["dependencies"]["zod"] == "4.6.7"
    assert (enabled / "src/lib/schemas/index.ts").is_file()
    assert yaml.safe_load((enabled / ".copier-answers.yml").read_text())["zod"] is True

    default = generate_project(
        NewRequest("plain-contract", "Plain contract test", tmp_path, template=str(TEMPLATE_DIR))
    ).destination
    assert "zod" not in json.loads((default / "package.json").read_text())["dependencies"]
    assert not (default / "src/lib/schemas").exists()
    assert yaml.safe_load((default / ".copier-answers.yml").read_text())["zod"] is False


# ---------------------------------------------------------------- release gate: snapshots versus the real template


def _capture(ref: str, version: str) -> dict:
    import sys

    sys.path.insert(0, str(PLATFORM_ROOT / "tools"))
    import capture_contract

    return capture_contract.capture(TEMPLATE_DIR, ref, version)


def _tags() -> set[str]:
    result = subprocess.run(["git", "-C", str(TEMPLATE_DIR), "tag"], capture_output=True, text=True, check=False)
    return set(result.stdout.split())


def test_each_committed_snapshot_still_matches_the_real_template(questions: dict) -> None:
    """The release gate. A tagged release must match its snapshot exactly; the newest snapshot may be
    compared with the working tree while that release is still unreleased."""
    import capture_contract  # noqa: F401  (tools/ is on the path through _capture)
    from test_contract_snapshots import SNAPSHOTS, load

    newest = max(SNAPSHOTS, key=lambda p: tuple(map(int, p.stem.split("."))))
    for path in SNAPSHOTS:
        tag = "v" + path.stem
        if tag in _tags():
            ref = tag
        elif path == newest:
            ref = "HEAD"
        else:
            pytest.fail(f"snapshot {path.name} has no matching tag {tag} in the template checkout")
        live = _capture(ref, path.stem)
        committed = load(path)
        drop = {"captured_from"}
        assert {k: v for k, v in live.items() if k not in drop} == {k: v for k, v in committed.items() if k not in drop}, (
            f"{path.name} drifted from the template at {ref}: run tools/capture_contract.py --ref {ref} --write"
        )


def test_an_older_supported_release_still_generates_with_its_own_options(questions: dict, tmp_path: Path) -> None:
    """Backward compatibility against the real v0.1.0 tag (skipped if the checkout has no such tag)."""
    if "v0.1.0" not in _tags():
        pytest.skip("the template checkout has no v0.1.0 tag")
    result = generate_project(
        NewRequest("legacy-contract", "Legacy contract test", tmp_path, template=str(TEMPLATE_DIR),
                   template_ref="v0.1.0", options=("cache_components=false",))
    )  # fmt: skip
    answers = yaml.safe_load((result.destination / ".copier-answers.yml").read_text())
    assert answers["cache_components"] is False and "zod" not in answers
    with pytest.raises(UsageError, match="needs template v0.2.0"):
        generate_project(NewRequest("no-zod", "x", tmp_path, template=str(TEMPLATE_DIR), template_ref="v0.1.0", options=("zod=true",)))
