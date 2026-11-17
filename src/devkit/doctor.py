"""Read-only workstation prerequisite checks (`devkit doctor`).

Nothing here installs, configures or modifies anything. Only version queries, `git config`
reads, `gh auth status` and `brew bundle check` are run. Their output is parsed for
versions or exit codes and never echoed, so no emails, tokens or config values are logged.
"""

from __future__ import annotations

import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .profiles import DEFAULT_PROFILE, PROFILES

Status = Literal["ok", "warn", "fail"]

MIN_PYTHON = (3, 12)
MIN_GIT = (2, 27)  # Copier requires git >= 2.27


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str


def _run(command: list[str], extra_env: dict[str, str] | None = None, timeout: int = 60):
    """Run a read-only command; return CompletedProcess, or None if it cannot run."""
    env = {**os.environ, **(extra_env or {})}
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            env=env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _version(text: str) -> tuple[int, ...] | None:
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    return tuple(int(part) for part in match.groups() if part is not None) if match else None


def _fmt(version: tuple[int, ...]) -> str:
    return ".".join(str(part) for part in version)


def required_node_major() -> int:
    """The Node.js major version generated projects pin, as declared by the Web Core profile."""
    template = PROFILES[DEFAULT_PROFILE].template
    assert template is not None
    return template.node_major


def _tool_version(binary: str, args: list[str]) -> tuple[int, ...] | None | Literal["missing"]:
    if shutil.which(binary) is None:
        return "missing"
    result = _run([binary, *args], timeout=15)
    if result is None or result.returncode != 0:
        return None
    return _version(result.stdout or result.stderr)


def check_python() -> Check:
    current = sys.version_info[:3]
    if current[:2] >= MIN_PYTHON:
        return Check("python", "ok", f"{_fmt(current)} (need >= {_fmt(MIN_PYTHON)})")
    return Check("python", "fail", f"{_fmt(current)}; need >= {_fmt(MIN_PYTHON)}")


def check_copier() -> Check:
    try:
        return Check("copier", "ok", f"{importlib.metadata.version('copier')} (project-local)")
    except importlib.metadata.PackageNotFoundError:
        return Check("copier", "fail", "not installed; run `uv sync` in the checkout")


def check_git() -> list[Check]:
    version = _tool_version("git", ["--version"])
    if version == "missing":
        return [Check("git", "fail", "not found on PATH")]
    if version is None:
        return [Check("git", "fail", "found but `git --version` failed")]
    checks = [
        Check("git", "ok" if version >= MIN_GIT else "fail", f"{_fmt(version)} (need >= {_fmt(MIN_GIT)})")
    ]
    identity = []
    for key in ("user.name", "user.email"):
        result = _run(["git", "config", "--get", key], timeout=15)
        identity.append(bool(result and result.returncode == 0 and result.stdout.strip()))
    if all(identity):
        checks.append(Check("git identity", "ok", "user.name and user.email are configured"))
    else:
        checks.append(Check("git identity", "warn", "user.name/user.email not both configured"))
    return checks


def check_node() -> list[Check]:
    major = required_node_major()
    node = _tool_version("node", ["--version"])
    checks: list[Check]
    if node == "missing":
        checks = [Check("node", "fail", f"not found on PATH; generated projects need Node {major}.x")]
    elif node is None:
        checks = [Check("node", "fail", "found but `node --version` failed")]
    elif node[0] == major:
        checks = [Check("node", "ok", f"{_fmt(node)} (generated projects pin {major}.x)")]
    else:
        checks = [
            Check("node", "fail", f"{_fmt(node)}; generated projects pin {major}.x")
        ]
    npm = _tool_version("npm", ["--version"])
    if npm == "missing":
        checks.append(Check("npm", "fail", "not found on PATH"))
    elif npm is None:
        checks.append(Check("npm", "fail", "found but `npm --version` failed"))
    else:
        checks.append(Check("npm", "ok", _fmt(npm)))
    return checks


def check_uv() -> Check:
    version = _tool_version("uv", ["--version"])
    if version == "missing":
        return Check("uv", "fail", "not found on PATH (brew install uv)")
    if version is None:
        return Check("uv", "fail", "found but `uv --version` failed")
    return Check("uv", "ok", _fmt(version))


def check_gh() -> list[Check]:
    version = _tool_version("gh", ["--version"])
    if version == "missing":
        return [Check("gh", "warn", "not found (needed later to create repositories)")]
    if version is None:
        return [Check("gh", "warn", "found but `gh --version` failed")]
    result = _run(["gh", "auth", "status"], timeout=30)
    authenticated = bool(result and result.returncode == 0)
    return [
        Check("gh", "ok", _fmt(version)),
        Check(
            "gh auth",
            "ok" if authenticated else "warn",
            "authenticated" if authenticated else "not authenticated (run `gh auth login`)",
        ),
    ]


def check_git_credentials() -> Check:
    """Is any git credential helper configured? Needed for private repositories.

    Only the presence of configuration is reported; helper commands and credentials are never
    read or printed.
    """
    if shutil.which("git") is None:
        return Check("git credentials", "warn", "skipped: git not found")
    result = _run(["git", "config", "--get-regexp", r"^credential\..*helper$"], timeout=15)
    if result is not None and result.returncode == 0 and result.stdout.strip():
        return Check("git credentials", "ok", "a credential helper is configured (private repositories)")
    return Check(
        "git credentials",
        "warn",
        "no credential helper configured; private template access needs one (`gh auth setup-git`)",
    )


def check_optional_tools() -> list[Check]:
    checks = []
    for binary, why in (
        ("brew", "installs Brewfile prerequisites"),
        ("fnm", "Node version manager (reads .nvmrc)"),
        ("docker", "needed by later milestones only"),
        ("mise", "evaluated, not required"),
    ):
        found = shutil.which(binary) is not None
        checks.append(Check(binary, "ok" if found else "warn", "found" if found else f"not found ({why})"))
    return checks


def check_brewfile(platform_root: Path) -> Check:
    brewfile = platform_root / "Brewfile"
    if sys.platform != "darwin":
        return Check("brewfile", "warn", "skipped: Homebrew checks are macOS-only")
    if shutil.which("brew") is None:
        return Check("brewfile", "warn", "skipped: brew not found")
    result = _run(
        ["brew", "bundle", "check", f"--file={brewfile}"],
        extra_env={"HOMEBREW_NO_AUTO_UPDATE": "1", "HOMEBREW_NO_ANALYTICS": "1"},
        timeout=120,
    )
    if result is not None and result.returncode == 0:
        return Check("brewfile", "ok", "all Brewfile entries are installed")
    return Check(
        "brewfile",
        "warn",
        "some Brewfile entries are missing; run `brew bundle check --verbose --file=Brewfile`",
    )


def run_checks(platform_root: Path) -> list[Check]:
    checks = [Check("platform", "ok", f"{sys.platform}")]
    checks.append(check_python())
    checks.append(check_copier())
    checks.extend(check_git())
    checks.extend(check_node())
    checks.append(check_uv())
    checks.extend(check_gh())
    checks.append(check_git_credentials())
    checks.extend(check_optional_tools())
    checks.append(check_brewfile(platform_root))
    return checks


def render(checks: list[Check]) -> str:
    labels = {"ok": "ok  ", "warn": "warn", "fail": "FAIL"}
    width = max(len(check.name) for check in checks)
    lines = [f"[{labels[c.status]}] {c.name.ljust(width)}  {c.detail}" for c in checks]
    failures = sum(c.status == "fail" for c in checks)
    warnings_ = sum(c.status == "warn" for c in checks)
    lines.append("")
    if failures:
        lines.append(f"{failures} required check(s) failed, {warnings_} warning(s).")
    else:
        lines.append(f"All required checks passed ({warnings_} warning(s)).")
    return "\n".join(lines)


def exit_code(checks: list[Check]) -> int:
    return 1 if any(check.status == "fail" for check in checks) else 0
