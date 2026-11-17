#!/usr/bin/env python3
"""Disposable workspaces with validated cleanup: the sanctioned way to delete directories here.

    uv run python tools/scratch.py new                 # prints a fresh, marked workspace path
    uv run python tools/scratch.py clean WORKSPACE     # removes that whole workspace
    uv run python tools/scratch.py clean WORKSPACE CHILD [CHILD ...]   # removes only those children

Why it exists: a recursive delete typed by hand is only as safe as the path in it. This helper
refuses to delete anything unless the path is provably inside a workspace it created itself:

* the workspace was made by `new_workspace` (it contains a marker file this tool wrote) and lives
  under the system temporary directory;
* the target resolves to a path strictly inside the workspace, is not a symbolic link, exists, and
  is a regular file or directory;
* neither is `/`, the home directory, the current directory, or a parent of either.

Validation is a separate pure function (`assert_removable`), so the rules are testable without
deleting anything, and the tests never point a delete at a system path.
"""

from __future__ import annotations

import argparse
import shutil
import stat
import sys
import tempfile
from pathlib import Path

MARKER = ".disposable-workspace"
MARKER_TEXT = "created by tools/scratch.py; safe to remove with `tools/scratch.py clean`\n"


class RefusedRemovalError(ValueError):
    """The path failed validation, so nothing was removed."""


def allowed_bases() -> list[Path]:
    """Workspaces may only live under these directories (resolved, so symlinks cannot disguise them)."""
    return [Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve()]


def new_workspace(prefix: str = "workspace-", base: Path | None = None) -> Path:
    """Create a unique, marked workspace under the temporary directory (or an allowed `base`)."""
    parent = Path(base).resolve() if base is not None else Path(tempfile.gettempdir()).resolve()
    workspace = Path(tempfile.mkdtemp(prefix=prefix, dir=parent)).resolve()
    (workspace / MARKER).write_text(MARKER_TEXT, encoding="utf-8")
    return workspace


def _is_inside(path: Path, parent: Path) -> bool:
    return path != parent and path.is_relative_to(parent)


def _check_workspace(workspace: Path) -> Path:
    if workspace.is_symlink():
        raise RefusedRemovalError(f"workspace is a symbolic link: {workspace}")
    resolved = workspace.resolve()
    marker = resolved / MARKER
    if not resolved.is_dir() or marker.is_symlink() or not marker.is_file():
        raise RefusedRemovalError(f"not a workspace created by this tool (no {MARKER}): {resolved}")
    if not any(_is_inside(resolved, base) for base in allowed_bases()):
        raise RefusedRemovalError(f"workspace is not under the system temporary directory: {resolved}")
    for protected, label in ((Path("/"), "the filesystem root"), (Path.home().resolve(), "the home directory"), (Path.cwd().resolve(), "the current directory")):
        if resolved == protected or resolved in protected.parents:
            raise RefusedRemovalError(f"workspace is, or contains, {label}: {resolved}")
    return resolved


def assert_removable(target: Path, workspace: Path) -> Path:
    """Return the resolved target if it may be deleted; raise RefusedRemovalError otherwise.

    Pure validation: never deletes anything.
    """
    root = _check_workspace(Path(workspace))
    candidate = Path(target)
    if candidate.is_symlink():
        raise RefusedRemovalError(f"refusing to remove a symbolic link: {candidate}")
    if not candidate.exists():
        raise RefusedRemovalError(f"does not exist: {candidate}")
    resolved = candidate.resolve()
    if resolved == root:
        raise RefusedRemovalError("the target is the workspace itself; use remove_workspace")
    if not _is_inside(resolved, root):
        raise RefusedRemovalError(f"{resolved} is outside the workspace {root}")
    if resolved.name == MARKER:
        raise RefusedRemovalError("refusing to remove the workspace marker")
    mode = resolved.lstat().st_mode
    if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
        raise RefusedRemovalError(f"not a regular file or directory: {resolved}")
    for protected, label in ((Path.home().resolve(), "the home directory"), (Path.cwd().resolve(), "the current directory")):
        if resolved == protected or resolved in protected.parents:
            raise RefusedRemovalError(f"target is, or contains, {label}: {resolved}")
    return resolved


def remove(target: Path, workspace: Path) -> None:
    """Delete `target` after it passes `assert_removable`."""
    resolved = assert_removable(target, workspace)
    if resolved.is_dir():
        shutil.rmtree(resolved)
    else:
        resolved.unlink()


def remove_workspace(workspace: Path) -> None:
    """Delete a whole workspace after it passes the workspace checks."""
    resolved = _check_workspace(Path(workspace))
    shutil.rmtree(resolved)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("new", help="create a marked workspace and print its path")
    make.add_argument("--prefix", default="workspace-")
    clean = commands.add_parser("clean", help="remove a workspace, or only the named children of it")
    clean.add_argument("workspace", type=Path)
    clean.add_argument("children", nargs="*", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "new":
            print(new_workspace(args.prefix))
            return 0
        if not args.children:
            remove_workspace(args.workspace)
            print(f"removed workspace {args.workspace}")
            return 0
        resolved = [assert_removable(child, args.workspace) for child in args.children]  # validate ALL first
        for child, path in zip(args.children, resolved):
            remove(path, args.workspace)
            print(f"removed {child}")
        return 0
    except RefusedRemovalError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
