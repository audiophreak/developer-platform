"""Non-interactive git invocations (argument lists only, never a shell)."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

_CREDENTIALS = re.compile(r"(?<=://)[^/@\s]+@")


def redact(text: str) -> str:
    """Remove `user:token@` credentials from anything that looks like a URL."""
    return _CREDENTIALS.sub("***@", text)


def git(
    *args: str, cwd: Path | None = None, timeout: int = 30
) -> subprocess.CompletedProcess[str] | None:
    """Run a read-only git command; None if git cannot be run or times out.

    Never prompts for credentials (a hung prompt would block the CLI) and never takes
    optional locks, so inspecting a repository does not modify it.
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            env=env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
