from __future__ import annotations

from pathlib import Path

import pytest

from conftest import PLATFORM_ROOT
from devkit import doctor
from devkit.doctor import Check


def test_required_node_major_comes_from_the_profile_registry() -> None:
    assert doctor.required_node_major() == 26


def test_missing_tools_fail_and_give_a_nonzero_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    checks = doctor.run_checks(PLATFORM_ROOT)
    by_name = {c.name: c for c in checks}
    for required in ("git", "node", "npm", "uv"):
        assert by_name[required].status == "fail", required
    assert by_name["python"].status == "ok"  # from the running interpreter, not PATH
    assert by_name["copier"].status == "ok"
    assert doctor.exit_code(checks) == 1
    assert "FAIL" in doctor.render(checks)


def test_exit_code_ignores_warnings() -> None:
    assert doctor.exit_code([Check("a", "ok", ""), Check("b", "warn", "")]) == 0
    assert doctor.exit_code([Check("a", "ok", ""), Check("b", "fail", "")]) == 1


def test_wrong_node_major_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "_tool_version", lambda binary, args: (22, 1, 0))
    checks = {c.name: c for c in doctor.check_node()}
    assert checks["node"].status == "fail"
    assert "26" in checks["node"].detail


def test_output_never_contains_git_identity_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\tname = Secret Person\n\temail = secret.person@example.invalid\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    # Keep this test offline and fast: the network/brew checks are covered separately.
    monkeypatch.setattr(doctor, "check_gh", lambda: [Check("gh", "ok", "stub")])
    monkeypatch.setattr(doctor, "check_brewfile", lambda root: Check("brewfile", "ok", "stub"))
    checks = doctor.run_checks(PLATFORM_ROOT)
    output = doctor.render(checks)
    assert "Secret Person" not in output and "secret.person" not in output
    identity = next(c for c in checks if c.name == "git identity")
    assert identity.status == "ok"


def test_git_identity_missing_is_a_warning_not_a_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    empty = tmp_path / "gitconfig"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(empty))
    monkeypatch.delenv("GIT_AUTHOR_NAME", raising=False)
    identity = next(c for c in doctor.check_git() if c.name == "git identity")
    assert identity.status == "warn"


def test_doctor_runs_against_the_real_machine() -> None:
    """Smoke: every check returns a result and the report renders. Pass/fail is machine-specific."""
    checks = doctor.run_checks(PLATFORM_ROOT)
    assert {"python", "copier", "git", "node", "npm", "uv"} <= {c.name for c in checks}
    assert all(c.status in {"ok", "warn", "fail"} for c in checks)
    assert doctor.render(checks).strip()


def test_git_credential_helper_presence_is_reported_without_leaking_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configured = tmp_path / "with-helper"
    configured.write_text('[credential "https://github.com"]\n\thelper = !secret-helper-command --token abc123\n')
    nothing = tmp_path / "without-helper"
    nothing.write_text("")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(nothing))

    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(configured))
    present = doctor.check_git_credentials()
    assert present.status == "ok"
    assert "secret-helper-command" not in present.detail and "abc123" not in present.detail

    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(nothing))
    absent = doctor.check_git_credentials()
    assert absent.status == "warn" and "gh auth setup-git" in absent.detail
    assert doctor.exit_code([present, absent]) == 0  # a missing helper is a warning, not a failure
