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
from .profiles import DEFAULT_PROFILE, Profile, get_profile, native_requirement
from .sources import ResolvedTemplate, release_version, resolve_template
from .validation import ensure_options_available, parse_options, validate_destination_name


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
    native_template: str | None = None  # the native iOS layer's checkout or origin (profile native-ios only)
    native_template_ref: str | None = None
    native_options: tuple[str, ...] = ()  # raw NAME=VALUE strings from --native-set


@dataclass(frozen=True)
class NewResult:
    destination: Path
    dry_run: bool
    template: ResolvedTemplate
    warnings: tuple[str, ...]
    native: ResolvedTemplate | None = None


def apply_profile_options(profile: Profile, options: dict[str, object]) -> dict[str, object]:
    """The profile's own options are part of what it is; its required ones must be stated by the person.

    A fixed option may be repeated with its own value but never changed. A required option (the database provider)
    is never defaulted: it is an architectural choice, so devkit asks for it instead of making it.
    """
    result = dict(options)
    for name, value in profile.fixed:
        if name in result and result[name] != value:
            raise UsageError(
                f"Profile {profile.id!r} sets {name}={str(value).lower()}; "
                f"--set {name}={str(result[name]).lower()} contradicts it. Use another profile instead."
            )
        result[name] = value
    for name in profile.required:
        if result.get(name) in (None, "none"):
            raise UsageError(
                f"Profile {profile.id!r} needs an explicit choice for {name} (devkit never picks an architecture "
                f"for you): add --set {name}=postgres or --set {name}=supabase."
            )
    return result


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
    options = apply_profile_options(profile, parse_options(spec, request.options))
    native_spec = profile.native
    if native_spec is None and (request.native_template or request.native_template_ref or request.native_options):
        raise UsageError(f"Profile {profile.id!r} has no native layer; --native-* options apply to the native-ios profile.")
    native_options = parse_options(native_spec, request.native_options) if native_spec else {}
    destination = resolve_destination(name, request.output_dir, root)

    template = resolve_template(spec, request.template, request.template_ref)
    if template.local_root is not None:
        _ensure_outside(destination, template.local_root, "the template checkout")
    ensure_options_available(spec, options, template)
    native = None
    if native_spec is not None:
        native = resolve_template(native_spec, request.native_template, request.native_template_ref)
        if native.local_root is not None:
            _ensure_outside(destination, native.local_root, "the native template checkout")
        ensure_options_available(native_spec, native_options, native)
        check_pair(template, native)
    if on_resolved is not None:
        on_resolved(template)

    # Copier validates app_name / app_description against the template's own rules.
    data: dict[str, object] = {"app_name": name, **options}
    if request.description is not None:
        data["app_description"] = request.description

    # With a native layer both layers are built in a staging directory beside the destination and moved into place
    # only when both succeeded, so a failure never leaves a half-built project at the name you asked for.
    staging = destination.parent / f".{name}.devkit-partial" if native is not None and not request.dry_run else None
    if staging is not None and os.path.lexists(staging):
        raise OperationError(f"{staging} exists from an earlier failed run. Inspect it, remove it yourself, and retry.")
    target = staging if staging is not None else destination

    try:
        with warnings.catch_warnings():
            # Reported once, more clearly, in `template.warnings`.
            warnings.simplefilter("ignore", DirtyLocalWarning)
            copier.run_copy(
                src_path=template.location,
                dst_path=target,
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

    if not request.dry_run:
        verify_options_recorded(target, options)

    if native is not None and native_spec is not None:
        apply_native_layer(
            native_spec, native, target if not request.dry_run else destination, name, native_options,
            pretend=request.dry_run, leftover=staging,
        )  # fmt: skip
        if staging is not None:
            if os.path.lexists(destination):
                raise OperationError(f"{destination} appeared while generating; the finished project is at {staging}.")
            os.rename(staging, destination)

    return NewResult(
        destination=destination,
        dry_run=request.dry_run,
        template=template,
        warnings=template.warnings + (native.warnings if native else ()),
        native=native,
    )


def check_pair(web: ResolvedTemplate, native: ResolvedTemplate) -> None:
    """A native release is generated against one web contract: refuse a pair whose releases do not belong together."""
    web_version, native_version = release_version(web), release_version(native)
    if web_version is None or native_version is None:
        return  # a development checkout on either side: the person is in charge
    required = native_requirement(native_version)
    if required is None:
        raise UsageError(f"native-ios-template {'.'.join(map(str, native_version))} is not known to this devkit.")
    if not required.contains(web_version):
        raise UsageError(
            f"native-ios-template v{'.'.join(map(str, native_version))} works with web-core-template {required}, "
            f"not v{'.'.join(map(str, web_version))} (its API client is generated from that web release's contract)."
        )


def apply_native_layer(
    spec, native: ResolvedTemplate, destination: Path, name: str, options: dict[str, object], *, pretend: bool, leftover: Path | None
) -> None:
    """Applies the native iOS template to a project directory: its own answers file, only `ios/`, no web file."""
    data: dict[str, object] = {"app_name": name, **options}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DirtyLocalWarning)
            copier.run_copy(
                src_path=native.location,
                dst_path=destination,
                data=data,
                vcs_ref=native.ref,
                settings=Settings(),
                defaults=True,
                overwrite=False,
                pretend=pretend,
                unsafe=False,
                quiet=False,
                cleanup_on_error=False,  # the web layer is already there: nothing is removed on failure
            )
    except ValueError as exc:
        if str(exc).startswith("Validation error for question"):
            raise UsageError(f"{exc}{_where(leftover)}") from exc
        raise OperationError(f"Applying the native iOS layer failed: {exc}.{_where(leftover)}") from exc
    except Exception as exc:
        raise OperationError(f"Applying the native iOS layer failed: {exc}.{_where(leftover)}") from exc
    if not pretend:
        verify_options_recorded(destination, options, spec.answers_file)
        if not (destination / "ios/App.xcodeproj").is_dir():
            raise OperationError(f"The native layer was applied but ios/App.xcodeproj is missing.{_where(leftover)}")


def _where(leftover: Path | None) -> str:
    return f" The web layer was generated but the project is incomplete and was NOT moved into place; inspect {leftover}." if leftover else ""


def _generation_failed(profile: str, exc: Exception, destination: Path) -> OperationError:
    leftover = (
        f" Partial output may remain at {destination}; inspect it before deleting."
        if os.path.lexists(destination)
        else ""
    )
    return OperationError(f"Generating profile {profile!r} failed: {exc}.{leftover}")


def verify_options_recorded(destination: Path, options: dict[str, object], answers_name: str = ".copier-answers.yml") -> None:
    """Defence in depth: every requested option must appear, with its value, in the answers file.

    Catches what the earlier checks cannot (a registry that is wrong about a release, a template
    that renamed a question): Copier would otherwise ignore the answer without a word.
    """
    if not options:
        return
    answers_file = destination / answers_name
    recorded = answers_file.read_text(encoding="utf-8") if answers_file.is_file() else ""
    for name, value in options.items():
        wanted = f"{name}: {str(value).lower() if isinstance(value, bool) else value}"
        if not any(line.strip() == wanted for line in recorded.splitlines()):
            raise OperationError(
                f"The project was generated, but option {name!r} was not recorded in its answers file, "
                f"so the template ignored it. Inspect {destination} before using it."
            )
