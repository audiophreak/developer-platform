"""Contract between this platform and the real web-core-template.

Needs a checkout of the template: `../web-core-template` next to this repository, or the path
in $WEB_CORE_TEMPLATE. Skipped when neither exists. This is the guard against the two
repositories drifting apart: the profile registry here must match what the template offers.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from conftest import PLATFORM_ROOT
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
        assert questions[option.name]["type"] == option.kind


def test_registry_node_major_matches_the_template_pin(questions: dict) -> None:
    nvmrc = (TEMPLATE_DIR / "template" / ".nvmrc").read_text().strip()
    assert int(nvmrc.split(".")[0]) == SPEC.node_major


def test_published_releases_are_not_older_than_the_supported_range(questions: dict) -> None:
    tags = list_release_tags(str(TEMPLATE_DIR))
    if not tags:
        pytest.skip("the template has no release tags yet")
    assert max(tags) >= SPEC.versions.minimum, "the registry supports releases that do not exist"


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
