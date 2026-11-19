"""Contract between this platform and the real native-ios-template (and the pair of real templates).

Needs checkouts of both templates: `../native-ios-template` and `../web-core-template` next to this repository, or the
paths in $NATIVE_IOS_TEMPLATE and $WEB_CORE_TEMPLATE. Skipped when either is missing. This is the release gate for the
`native-ios` profile: the registry matches the real native questions, and a real composed project holds the same API
contract in both layers.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import PLATFORM_ROOT
from devkit.generate import NewRequest, generate_project
from devkit.profiles import NATIVE_TEMPLATE

pytestmark = pytest.mark.integration

WEB = Path(os.environ.get("WEB_CORE_TEMPLATE", PLATFORM_ROOT.parent / "web-core-template"))
NATIVE = Path(os.environ.get("NATIVE_IOS_TEMPLATE", PLATFORM_ROOT.parent / "native-ios-template"))


@pytest.fixture(scope="module")
def questions() -> dict:
    if not (NATIVE / "copier.yml").is_file() or not (WEB / "copier.yml").is_file():
        pytest.skip("needs checkouts of web-core-template and native-ios-template")
    config = yaml.safe_load((NATIVE / "copier.yml").read_text())
    assert config["_answers_file"] == NATIVE_TEMPLATE.answers_file
    return {k: v for k, v in config.items() if not k.startswith("_")}


def test_every_native_registry_option_is_a_question_with_the_registered_default(questions: dict) -> None:
    for option in NATIVE_TEMPLATE.options:
        assert option.name in questions, option.name
        question = questions[option.name]
        assert question["type"] == option.kind, option.name
        if option.default is not None:
            assert str(question["default"]) == str(option.default), option.name
    assert {"app_name"} <= set(questions)


def test_the_real_pair_composes_one_project_with_two_records_and_one_api_contract(questions: dict, tmp_path: Path) -> None:
    result = generate_project(
        NewRequest(
            "pair-app", "Pair contract test", tmp_path, profile="native-ios", template=str(WEB), native_template=str(NATIVE),
            options=("database=postgres",), native_options=("debug_api_port=3100",),
        )
    )  # fmt: skip
    project = result.destination
    web, ios = (yaml.safe_load((project / name).read_text()) for name in (".copier-answers.yml", ".copier-answers.ios.yml"))
    assert (web["zod"], web["rest_api"], web["auth"], web["native_client"], web["database"]) == (True, True, True, True, "postgres")
    assert ios["app_name"] == "pair-app" and ios["debug_api_port"] == 3100 and "database" not in ios
    assert (project / "ios/App.xcodeproj/project.pbxproj").is_file() and (project / "openapi/openapi.json").is_file()
    # the property the whole design rests on: the client was generated from the contract this web part serves
    assert (project / "openapi/openapi.json").read_bytes() == (project / "ios/Contract/openapi.json").read_bytes(), (
        "the native template was released against a different web contract: re-sync it (ios/scripts/sync-contract.sh)"
    )
    check = subprocess.run(["sh", "scripts/check-contract.sh"], cwd=project / "ios", capture_output=True, text=True)
    assert check.returncode == 0 and "matches the web project's" in check.stdout, check.stderr
    assert "ios" in (project / ".prettierignore").read_text()  # the web tooling leaves the native layer alone
