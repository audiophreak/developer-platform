"""Resolving where a profile's template comes from, and exactly which version.

Two modes:

- **published** (default): the profile's template origin (a git URL) at the newest release tag
  this devkit supports. Generated projects record that portable URL and a release tag.
- **local** (`--template PATH`): a template checkout on this machine, used as-is (working tree
  included) unless `--template-ref` names a ref. For developing the template; the generated
  project records a home-relative path, so it is not portable.

`--template URL` uses a different origin in published mode (newest supported tag, or
`--template-ref`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .errors import TemplateUnavailableError, UsageError
from .gitutil import git, redact
from .profiles import TemplateSpec, Version

_RELEASE_TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)")


@dataclass(frozen=True)
class SourceInfo:
    is_git_root: bool
    has_commits: bool
    dirty: bool


@dataclass(frozen=True)
class ResolvedTemplate:
    location: str  # what Copier is given, and records in `.copier-answers.yml`
    ref: str | None  # exact git ref rendered (None: Copier decides, for repos with no commits)
    mode: Literal["published", "local"]
    local_root: Path | None  # the checkout, for local mode
    warnings: tuple[str, ...] = ()


def parse_release_tag(name: str) -> Version | None:
    """`v1.2.3` -> (1, 2, 3). Anything else (pre-releases, branches, other tags) -> None."""
    match = _RELEASE_TAG.fullmatch(name)
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def format_tag(version: Version) -> str:
    return "v" + ".".join(map(str, version))


def list_release_tags(location: str) -> list[Version]:
    """All `vMAJOR.MINOR.PATCH` tags at `location` (a URL or a local path), oldest first."""
    result = git("ls-remote", "--tags", "--refs", location, timeout=60)
    if result is None:
        raise TemplateUnavailableError(
            f"Cannot read template releases from {redact(location)}: git could not be run."
        )
    if result.returncode != 0:
        reason = redact(result.stderr.strip().splitlines()[-1]) if result.stderr.strip() else ""
        raise TemplateUnavailableError(
            f"Template source is unavailable: {redact(location)}"
            + (f" ({reason[:200]})" if reason else "")
            + ". Check the address. If the repository is private, git must be able to "
            "authenticate without prompting (a credential helper; see docs/publishing.md, "
            "'Private repositories'). Or use --template to point at a local checkout."
        )
    versions = []
    for line in result.stdout.splitlines():
        _, _, ref = line.partition("\trefs/tags/")
        version = parse_release_tag(ref.strip())
        if version is not None:
            versions.append(version)
    return sorted(set(versions))


def inspect_checkout(root: Path) -> SourceInfo:
    top = git("rev-parse", "--show-toplevel", cwd=root)
    is_git_root = bool(
        top and top.returncode == 0 and Path(top.stdout.strip()).resolve() == root.resolve()
    )
    if not is_git_root:
        return SourceInfo(False, False, False)
    head = git("rev-parse", "--verify", "--quiet", "HEAD", cwd=root)
    status = git("status", "--porcelain", cwd=root)
    return SourceInfo(
        is_git_root=True,
        has_commits=bool(head and head.returncode == 0),
        dirty=bool(status and status.stdout.strip()),
    )


def recordable_path(root: Path, info: SourceInfo, home: Path | None = None) -> str:
    """How a local checkout is recorded in the generated `.copier-answers.yml`.

    Copier records the string it is given. A home-relative path (`~/...`) is understood by
    Copier for git repository roots and keeps the user name and absolute paths out of generated
    projects. Anything else is recorded as an absolute path.
    """
    root = root.resolve()
    if info.is_git_root:
        try:
            relative = root.relative_to((home or Path.home()).resolve())
        except ValueError:
            return str(root)
        return f"~/{relative.as_posix()}"
    return str(root)


def _resolve_release(spec: TemplateSpec, location: str, ref: str | None) -> str:
    """Pick the release tag to render from `location`, enforcing the supported range."""
    supported = spec.versions
    if ref is not None:
        version = parse_release_tag(ref)
        if version is None:
            raise UsageError(
                f"--template-ref {ref!r} is not a release tag (vMAJOR.MINOR.PATCH). Branches and "
                "commits are only allowed with --template pointing at a local checkout."
            )
        if not supported.contains(version):
            raise UsageError(
                f"Template release {ref} is outside the range this devkit supports "
                f"({supported}). Use a supported release or a matching devkit."
            )
        if version not in list_release_tags(location):
            raise TemplateUnavailableError(
                f"Release {ref} does not exist at {redact(location)}."
            )
        return ref
    candidates = [v for v in list_release_tags(location) if supported.contains(v)]
    if not candidates:
        raise TemplateUnavailableError(
            f"No supported template release found at {redact(location)} "
            f"(this devkit supports {supported}). Has the first release been tagged?"
        )
    return format_tag(max(candidates))


def _is_bare_repository(path: Path) -> bool:
    """A bare repository is an origin to fetch releases from, not a checkout to render."""
    return (path / "HEAD").is_file() and (path / "objects").is_dir() and not (path / ".git").exists()


def resolve_template(
    spec: TemplateSpec, template: str | None = None, template_ref: str | None = None
) -> ResolvedTemplate:
    if template is not None:
        candidate = Path(template).expanduser()
        if candidate.is_dir() and not _is_bare_repository(candidate):
            return _resolve_local(candidate, template_ref)
    location = template if template is not None else spec.url
    return ResolvedTemplate(
        location=location,
        ref=_resolve_release(spec, location, template_ref),
        mode="published",
        local_root=None,
    )


def _resolve_local(directory: Path, ref: str | None) -> ResolvedTemplate:
    root = directory.resolve()
    if not (root / "copier.yml").is_file():
        raise UsageError(f"Not a Copier template (no copier.yml): {root}")
    info = inspect_checkout(root)
    notes: list[str] = []
    if ref is None:
        # Development loop: render the checkout as it is on disk.
        if not info.is_git_root:
            notes.append(
                "The template is not a git repository, so the project records an absolute path "
                "and cannot be upgraded with `copier update`."
            )
        elif not info.has_commits:
            notes.append(
                "The template repository has no commits, so the project cannot be upgraded "
                "until the template is committed and tagged."
            )
        elif info.dirty:
            notes.append(
                "The template has uncommitted changes. They are included in this project but "
                "not recorded, so a later `copier update` may show spurious differences."
            )
        ref = "HEAD" if info.has_commits else None
    elif not info.is_git_root:
        raise UsageError(f"--template-ref needs a git repository, but {root} is not one.")
    notes.append(
        "Local template mode: the project records a local path and is for development, "
        "not for sharing."
    )
    return ResolvedTemplate(
        location=recordable_path(root, info),
        ref=ref,
        mode="local",
        local_root=root,
        warnings=tuple(notes),
    )


__all__ = [
    "ResolvedTemplate",
    "SourceInfo",
    "format_tag",
    "inspect_checkout",
    "list_release_tags",
    "parse_release_tag",
    "recordable_path",
    "resolve_template",
]
