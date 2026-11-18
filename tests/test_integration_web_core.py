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


def test_local_mode_selects_forms_with_zod_in_the_real_template(questions: dict, tmp_path: Path) -> None:
    import json

    project = generate_project(
        NewRequest("forms-contract", "Forms contract test", tmp_path, template=str(TEMPLATE_DIR), options=("zod=true", "forms=true"))
    ).destination
    dependencies = json.loads((project / "package.json").read_text())["dependencies"]
    assert dependencies["react-hook-form"] == "7.91.0" and dependencies["@hookform/resolvers"] == "5.9.2"
    assert (project / "src/components/forms/example-form.tsx").is_file()
    recorded = yaml.safe_load((project / ".copier-answers.yml").read_text())
    assert (recorded["zod"], recorded["forms"]) == (True, True)


def test_the_real_template_itself_rejects_forms_without_zod_and_devkit_adds_no_rule(questions: dict, tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="forms requires zod") as raised:
        generate_project(NewRequest("no-zod", "x", tmp_path, template=str(TEMPLATE_DIR), options=("forms=true",)))
    assert raised.value.exit_code == 2
    assert not (tmp_path / "no-zod").exists()


def test_local_mode_selects_rest_api_with_and_without_forms_in_the_real_template(questions: dict, tmp_path: Path) -> None:
    for name, extra in (("api-contract", ()), ("api-forms-contract", ("forms=true",))):
        project = generate_project(
            NewRequest(name, "REST API contract test", tmp_path, template=str(TEMPLATE_DIR), options=("zod=true", "rest_api=true", *extra))
        ).destination
        for relative in ("src/app/api/v1/app-info/route.ts", "src/app/api/v1/examples/validate/route.ts", "src/server/api/responses.ts", "docs/api-v1.md"):
            assert (project / relative).is_file(), relative
        recorded = yaml.safe_load((project / ".copier-answers.yml").read_text())
        assert (recorded["zod"], recorded["rest_api"], recorded["forms"]) == (True, True, bool(extra))


def test_the_real_template_itself_rejects_rest_api_without_zod(questions: dict, tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="rest_api requires zod") as raised:
        generate_project(NewRequest("api-no-zod", "x", tmp_path, template=str(TEMPLATE_DIR), options=("rest_api=true",)))
    assert raised.value.exit_code == 2
    assert not (tmp_path / "api-no-zod").exists()


def test_every_registry_choice_is_exactly_the_templates_set_of_choices(questions: dict) -> None:
    for option in SPEC.options:
        if option.choices:
            assert questions[option.name]["choices"] == list(option.choices), option.name


@pytest.mark.parametrize("provider", ["postgres", "supabase"])
def test_local_mode_generates_a_database_application_with_each_provider(questions: dict, tmp_path: Path, provider: str) -> None:
    project = generate_project(
        NewRequest(f"{provider}-contract", "Database contract test", tmp_path, template=str(TEMPLATE_DIR), options=("zod=true", f"database={provider}"))
    ).destination
    recorded = yaml.safe_load((project / ".copier-answers.yml").read_text())
    assert (recorded["zod"], recorded["database"]) == (True, provider)
    for relative in ("supabase/migrations/20260101000000_create_items.sql", "scripts/db/cli.mjs", "src/server/items/repository.ts", "docs/database.md"):
        assert (project / relative).is_file(), relative
    assert (project / "compose.yaml").is_file() == (provider == "postgres")
    assert (project / "supabase/config.toml").is_file() == (provider == "supabase")


def test_the_real_template_itself_rejects_a_database_without_zod_and_devkit_adds_no_rule(questions: dict, tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="database requires zod") as raised:
        generate_project(NewRequest("db-no-zod", "x", tmp_path, template=str(TEMPLATE_DIR), options=("database=postgres",)))
    assert raised.value.exit_code == 2
    assert not (tmp_path / "db-no-zod").exists()
    with pytest.raises(UsageError, match="must be one of none, postgres, supabase"):  # devkit's own check, before the template is read
        generate_project(NewRequest("db-bad", "x", tmp_path, template=str(TEMPLATE_DIR), options=("zod=true", "database=oracle")))
    assert not (tmp_path / "db-bad").exists()


@pytest.mark.parametrize("provider", ["postgres", "supabase"])
def test_local_mode_generates_an_auth_application_with_each_provider(questions: dict, tmp_path: Path, provider: str) -> None:
    project = generate_project(
        NewRequest(f"{provider}-auth", "Auth contract test", tmp_path, template=str(TEMPLATE_DIR),
                   options=("zod=true", "rest_api=true", f"database={provider}", "auth=true"))
    ).destination  # fmt: skip
    recorded = yaml.safe_load((project / ".copier-answers.yml").read_text())
    assert (recorded["zod"], recorded["rest_api"], recorded["database"], recorded["auth"]) == (True, True, provider, True)
    for relative in ("src/server/auth/auth.ts", "src/server/auth/scope.ts", "src/app/api/auth/[...all]/route.ts", "src/app/api/v1/items/route.ts",
                     "supabase/migrations/20260301000000_create_auth.sql", "scripts/db/roles.mjs", "docs/auth.md", ".npmrc"):  # fmt: skip
        assert (project / relative).is_file(), relative


@pytest.mark.parametrize(
    ("options", "message"),
    [(("auth=true",), "auth requires zod"), (("zod=true", "auth=true"), "auth requires rest_api"),
     (("zod=true", "rest_api=true", "auth=true"), "auth requires a database")],
)  # fmt: skip
def test_the_real_template_itself_rejects_auth_without_its_prerequisites_and_devkit_adds_no_rule(questions: dict, tmp_path: Path, options, message: str) -> None:
    with pytest.raises(UsageError, match=message) as raised:
        generate_project(NewRequest("auth-missing", "x", tmp_path, template=str(TEMPLATE_DIR), options=options))
    assert raised.value.exit_code == 2
    assert not (tmp_path / "auth-missing").exists()


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


def test_the_real_v0_2_0_release_still_generates_and_refuses_forms(questions: dict, tmp_path: Path) -> None:
    """Backward compatibility against the real v0.2.0 tag (skipped if the checkout has no such tag)."""
    if "v0.2.0" not in _tags():
        pytest.skip("the template checkout has no v0.2.0 tag")
    result = generate_project(
        NewRequest("v020-contract", "v0.2.0 contract test", tmp_path, template=str(TEMPLATE_DIR),
                   template_ref="v0.2.0", options=("zod=true",))
    )  # fmt: skip
    answers = yaml.safe_load((result.destination / ".copier-answers.yml").read_text())
    assert answers["zod"] is True and "forms" not in answers
    with pytest.raises(UsageError, match="'forms' needs template v0.3.0"):
        generate_project(NewRequest("no-forms", "x", tmp_path, template=str(TEMPLATE_DIR), template_ref="v0.2.0", options=("zod=true", "forms=true")))
    assert not (tmp_path / "no-forms").exists()


def test_the_real_v0_3_0_release_still_generates_and_refuses_rest_api(questions: dict, tmp_path: Path) -> None:
    """Backward compatibility against the real v0.3.0 tag (skipped if the checkout has no such tag)."""
    if "v0.3.0" not in _tags():
        pytest.skip("the template checkout has no v0.3.0 tag")
    result = generate_project(
        NewRequest("v030-contract", "v0.3.0 contract test", tmp_path, template=str(TEMPLATE_DIR),
                   template_ref="v0.3.0", options=("zod=true", "forms=true"))
    )  # fmt: skip
    recorded = yaml.safe_load((result.destination / ".copier-answers.yml").read_text())
    assert recorded["forms"] is True and "rest_api" not in recorded
    with pytest.raises(UsageError, match="'rest_api' needs template v0.4.0"):
        generate_project(NewRequest("no-api", "x", tmp_path, template=str(TEMPLATE_DIR), template_ref="v0.3.0", options=("zod=true", "rest_api=true")))
    assert not (tmp_path / "no-api").exists()


def test_the_real_v0_4_0_release_still_generates_and_refuses_a_database(questions: dict, tmp_path: Path) -> None:
    """Backward compatibility against the real v0.4.0 tag (skipped if the checkout has no such tag)."""
    if "v0.4.0" not in _tags():
        pytest.skip("the template checkout has no v0.4.0 tag")
    result = generate_project(
        NewRequest("v040-contract", "v0.4.0 contract test", tmp_path, template=str(TEMPLATE_DIR),
                   template_ref="v0.4.0", options=("zod=true", "forms=true", "rest_api=true"))
    )  # fmt: skip
    recorded = yaml.safe_load((result.destination / ".copier-answers.yml").read_text())
    assert recorded["rest_api"] is True and "database" not in recorded
    with pytest.raises(UsageError, match="'database' needs template v0.5.0"):
        generate_project(NewRequest("no-db", "x", tmp_path, template=str(TEMPLATE_DIR), template_ref="v0.4.0", options=("zod=true", "database=postgres")))
    assert not (tmp_path / "no-db").exists()


def test_the_real_v0_5_1_release_still_generates_and_refuses_auth(questions: dict, tmp_path: Path) -> None:
    """Backward compatibility against the real v0.5.1 tag (skipped if the checkout has no such tag)."""
    if "v0.5.1" not in _tags():
        pytest.skip("the template checkout has no v0.5.1 tag")
    result = generate_project(
        NewRequest("v051-contract", "v0.5.1 contract test", tmp_path, template=str(TEMPLATE_DIR),
                   template_ref="v0.5.1", options=("zod=true", "rest_api=true", "database=supabase"))
    )  # fmt: skip
    recorded = yaml.safe_load((result.destination / ".copier-answers.yml").read_text())
    assert recorded["database"] == "supabase" and "auth" not in recorded
    with pytest.raises(UsageError, match="'auth' needs template v0.6.0"):
        generate_project(NewRequest("no-auth", "x", tmp_path, template=str(TEMPLATE_DIR), template_ref="v0.5.1", options=("zod=true", "rest_api=true", "database=postgres", "auth=true")))
    assert not (tmp_path / "no-auth").exists()
