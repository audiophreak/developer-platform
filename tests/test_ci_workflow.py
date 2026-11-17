"""The CI workflow stays minimal, pinned and least-privilege, and collects test evidence.

Evidence means: machine-readable JUnit XML and the console record of every run, tied to the exact
commit and Python version, uploaded even when tests fail, without weakening the exit code and
without any credential or environment data in the artifact (docs/ci-evidence.md).
"""

from __future__ import annotations

import re

import yaml

from conftest import PLATFORM_ROOT

WORKFLOW = PLATFORM_ROOT / ".github" / "workflows" / "ci.yml"
REPORT_STEPS = ("Record run metadata", "Summarize results", "Check reports contain no token-shaped strings", "Upload test reports")


def _load() -> tuple[str, dict]:
    text = WORKFLOW.read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def _job() -> dict:
    _, workflow = _load()
    (job,) = workflow["jobs"].values()
    return job


def _step(name_start: str) -> dict:
    return next(s for s in _job()["steps"] if s.get("name", "").startswith(name_start))


def _names() -> list[str]:
    return [s.get("name", "") for s in _job()["steps"]]


# ------------------------------------------------------------------ security and structure


def test_triggers_are_push_to_main_and_pull_request_only() -> None:
    _, workflow = _load()
    triggers = workflow[True] if True in workflow else workflow["on"]  # YAML reads `on:` as True
    assert set(triggers) == {"push", "pull_request"}
    assert triggers["push"] == {"branches": ["main"]}


def test_permissions_are_read_only_and_never_widened() -> None:
    text, workflow = _load()
    assert workflow["permissions"] == {"contents": "read"}
    assert "permissions" not in _job()
    assert "pull_request_target" not in text and "secrets." not in text and "GITHUB_TOKEN" not in text


def test_every_action_is_pinned_to_a_full_commit_sha_with_a_version_comment() -> None:
    text, _ = _load()
    uses = [s["uses"] for s in _job()["steps"] if "uses" in s]
    assert len(uses) == 3 and any(u.startswith("actions/upload-artifact@") for u in uses)
    for reference in uses:
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", reference), reference
        assert re.search(re.escape(reference) + r" # v\d+\.\d+\.\d+", text), reference


def test_checkout_does_not_persist_credentials() -> None:
    checkout = next(s for s in _job()["steps"] if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["persist-credentials"] is False


def test_the_job_has_a_timeout_and_the_matrix_covers_the_python_floor_and_newest() -> None:
    job = _job()
    assert 0 < job["timeout-minutes"] <= 60 and job["runs-on"] == "ubuntu-latest"
    assert job["strategy"]["fail-fast"] is False
    assert job["strategy"]["matrix"]["python-version"] == ["3.12", "3.14"]
    floor = re.search(r'requires-python = ">=(\d+)\.(\d+)"', (PLATFORM_ROOT / "pyproject.toml").read_text())
    assert "3.12" == f"{floor[1]}.{floor[2]}", "the declared floor must be tested"


def test_installation_is_locked_and_uv_is_pinned_exactly() -> None:
    runs = [s["run"] for s in _job()["steps"] if "run" in s and "name" not in s]
    assert runs[1] == "uv sync --locked"
    assert re.fullmatch(r"python -m pip install uv==\d+\.\d+\.\d+", runs[0])


def test_no_run_script_dumps_the_environment_or_traces_commands() -> None:
    for step in _job()["steps"]:
        script = step.get("run", "")
        assert not re.search(r"(^|[\s;|&])(env|printenv|export)\s*($|[|>;&])", script, re.MULTILINE), script
        assert not re.search(r"\bset\s+-[a-z]*x|\bset\s+-o\s+xtrace", script), script
        assert "echo $" not in script and "toJSON(secrets" not in script


# ------------------------------------------------------------------ evidence


def test_the_commit_under_test_is_the_pull_request_head_not_the_synthetic_merge_commit() -> None:
    assert _job()["env"]["EVIDENCE_COMMIT"] == "${{ github.event.pull_request.head.sha || github.sha }}"


def test_the_test_step_writes_junit_and_a_console_record_and_keeps_the_exit_code() -> None:
    text, _ = _load()
    step = _step("Test")
    script = step["run"]
    assert step["shell"] == "bash"  # bash -eo pipefail: pytest's failure survives the pipe to tee
    assert "continue-on-error" not in text
    assert "uv run --locked pytest" in script
    assert "--junitxml=reports/junit.xml" in script
    assert "tee reports/pytest-output.txt" in script and "2>&1" in script
    assert "-rfEs" in script  # failures, errors and skips are reported with their reasons
    assert "junit_logging=no" in script and "junit_family=xunit2" in script  # no captured output in the XML
    assert "${EVIDENCE_COMMIT}" in script and "matrix.python-version" in script  # in the suite name


def test_reports_are_written_after_the_tests_and_always_run() -> None:
    names = _names()
    assert [n for n in names if n in REPORT_STEPS] == list(REPORT_STEPS)  # in this order
    test_index = next(i for i, n in enumerate(names) if n.startswith("Test"))
    for name in REPORT_STEPS:
        assert names.index(name) > test_index
        assert _step(name)["if"].startswith("always()"), f"{name} must run even when the tests fail"


def test_metadata_ties_the_reports_to_the_commit_python_and_dependencies() -> None:
    script = _step("Record run metadata")["run"]
    for needle in ("commit_under_test=${EVIDENCE_COMMIT}", "github_sha=${GITHUB_SHA}", "run_id=", "run_attempt=",
                   "matrix_python=", "python=$(python --version", "uv_lock_sha256=", "pytest=", "uv pip freeze --exclude-editable"):  # fmt: skip
        assert needle in script, needle


def test_the_summary_shows_the_tail_of_the_console_record() -> None:
    script = _step("Summarize results")["run"]
    assert '"$GITHUB_STEP_SUMMARY"' in script and "tail -n" in script and "reports/pytest-output.txt" in script


def test_reports_are_scanned_for_tokens_before_upload_and_a_hit_blocks_the_upload() -> None:
    scan, upload = _step("Check reports contain no token-shaped strings"), _step("Upload test reports")
    assert scan["id"] == "scan" and "exit 1" in scan["run"]
    for shape in ("gh[pousr]_", "github_pat_", "PRIVATE KEY", "AKIA"):
        assert shape in scan["run"], shape
    assert upload["if"] == "always() && steps.scan.outcome == 'success'"


def test_the_artifact_is_unique_per_python_and_commit_bounded_and_fails_if_empty() -> None:
    upload = _step("Upload test reports")
    assert upload["uses"].startswith("actions/upload-artifact@")
    with_ = upload["with"]
    assert with_["path"] == "reports/"  # nothing outside the reports directory
    assert "matrix.python-version" in with_["name"] and "env.EVIDENCE_COMMIT" in with_["name"]
    assert with_["if-no-files-found"] == "error"
    assert 1 <= with_["retention-days"] <= 30
