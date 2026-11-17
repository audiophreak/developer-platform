"""Locating the developer-platform checkout (where the Brewfile lives)."""

from __future__ import annotations

from pathlib import Path


class PlatformRootNotFoundError(RuntimeError):
    """devkit is not running from a developer-platform checkout."""


def find_platform_root(start: Path | None = None) -> Path:
    """Walk up from this file to the checkout root (the directory holding Brewfile and src/devkit)."""
    here = (start or Path(__file__)).resolve()
    for parent in here.parents:
        if (parent / "Brewfile").is_file() and (parent / "src" / "devkit").is_dir():
            return parent
    raise PlatformRootNotFoundError(
        "Cannot find the developer-platform checkout (Brewfile and src/devkit). "
        "Run devkit from a checkout, for example: uv run devkit --help"
    )
