"""Create a new application from a profile's Copier template (`devkit new`)."""

from __future__ import annotations

import os
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import copier
from copier import Settings
from copier.errors import DirtyLocalWarning

from .errors import OperationError, UsageError
from .paths import find_platform_root
from .profiles import DEFAULT_PROFILE, get_profile
from .sources import ResolvedTemplate, resolve_template
from .validation import parse_options, validate_destination_name


@dataclass(frozen=True)
class NewRequest:
    name: str
    description: str | None = None  # None: the template's own default
    output_dir: Path = field(default_factory=Path.cwd)
    profile: str = DEFAULT_PROFILE
    dry_run: bool = False
    template: str | None = None  # local checkout (development) or alternative origin URL
    template_ref: str | None = None
    options: tuple[str, ...] = ()  # raw NAME=VALUE strings from --set


@dataclass(frozen=True)
class NewResult:
    destination: Path
    dry_run: bool
    template: ResolvedTemplate
    warnings: tuple[str, ...]


def _ensure_outside(destination: Path, root: Path, what: str) -> None:
    if destination.is_relative_to(root.resolve()):
        raise OperationError(
            f"Destination is inside {what}: {destination}. Choose an output directory outside it."
        )


def resolve_destination(name: str, output_dir: Path, platform_root: Path) -> Path:
    """Return the destination path, refusing anything that could overwrite data."""
    output_dir = Path(output_dir).expanduser()
    if not output_dir.is_dir():
        raise OperationError(f"Output directory does not exist: {output_dir}")
    destination = output_dir.resolve() / name
    if os.path.lexists(destination):
        raise OperationError(
            f"Destination already exists: {destination}. Refusing to overwrite it; "
            "choose another name or --output-dir."
        )
    _ensure_outside(destination, platform_root, "the developer-platform checkout")
    return destination


def generate_project(
    request: NewRequest,
    platform_root: Path | None = None,
    on_resolved: Callable[[ResolvedTemplate], None] | None = None,
) -> NewResult:
    root = (platform_root or find_platform_root()).resolve()

    # Cheap checks first, so nothing touches the network or the filesystem on bad input.
    profile = get_profile(request.profile)  # raises for reserved or unknown profiles
    spec = profile.template
    assert spec is not None  # guaranteed for available profiles
    name = validate_destination_name(request.name)
    options = parse_options(spec, request.options)
    destination = resolve_destination(name, request.output_dir, root)

    template = resolve_template(spec, request.template, request.template_ref)
    if template.local_root is not None:
        _ensure_outside(destination, template.local_root, "the template checkout")
    if on_resolved is not None:
        on_resolved(template)

    # Copier validates app_name / app_description against the template's own rules.
    data: dict[str, object] = {"app_name": name, **options}
    if request.description is not None:
        data["app_description"] = request.description

    try:
        with warnings.catch_warnings():
            # Reported once, more clearly, in `template.warnings`.
            warnings.simplefilter("ignore", DirtyLocalWarning)
            copier.run_copy(
                src_path=template.location,
                dst_path=destination,
                data=data,
                vcs_ref=template.ref,
                settings=Settings(),  # ignore any user-level Copier settings
                defaults=True,
                overwrite=False,
                pretend=request.dry_run,
                unsafe=False,
                quiet=False,
                cleanup_on_error=True,
            )
    except ValueError as exc:
        if str(exc).startswith("Validation error for question"):
            raise UsageError(str(exc)) from exc
        raise _generation_failed(profile.id, exc, destination) from exc
    except Exception as exc:  # Copier raises many error types; report them uniformly.
        raise _generation_failed(profile.id, exc, destination) from exc

    return NewResult(
        destination=destination,
        dry_run=request.dry_run,
        template=template,
        warnings=template.warnings,
    )


def _generation_failed(profile: str, exc: Exception, destination: Path) -> OperationError:
    leftover = (
        f" Partial output may remain at {destination}; inspect it before deleting."
        if os.path.lexists(destination)
        else ""
    )
    return OperationError(f"Generating profile {profile!r} failed: {exc}.{leftover}")
