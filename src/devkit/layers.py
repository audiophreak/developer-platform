"""The two template layers of a native project: adding the native layer to a web project, and reporting both.

A project made by the `native-ios` profile (or given the layer later with `devkit native add`) is one directory with
two Copier templates applied to it, each with its own answers file and its own releases:

- the web layer: `.copier-answers.yml`, from web-core-template;
- the native layer: `.copier-answers.ios.yml`, from native-ios-template, which owns only `ios/`.

They are upgraded one at a time (`devkit upgrade --layer web|native`), each from a clean git tree and each left for you to
review and commit, so a failure in one never leaves the project looking fully upgraded. `devkit status` shows both.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import OperationError, UsageError
from .generate import apply_native_layer, check_pair
from .profiles import NATIVE_TEMPLATE, PROFILES, Version, get_profile, native_requirement
from .sources import ResolvedTemplate, format_tag, list_release_tags, parse_release_tag, resolve_template
from .upgrade import ANSWERS_FILE, NATIVE_ANSWERS_FILE, _clean_repository, _installed_release, read_answers
from .validation import ensure_options_available, parse_options


@dataclass(frozen=True)
class AddNativeRequest:
    project: Path
    native_template: str | None = None
    native_template_ref: str | None = None
    native_options: tuple[str, ...] = ()
    dry_run: bool = False


@dataclass(frozen=True)
class LayerStatus:
    layer: str
    installed: Version | None
    newest: Version | None  # newest supported release at the recorded origin
    note: str = ""

    @property
    def pending(self) -> bool:
        return self.installed is not None and self.newest is not None and self.newest > self.installed


def add_native_layer(request: AddNativeRequest) -> ResolvedTemplate:
    """Applies the native iOS layer to an existing full-stack project. Adds files; changes none of yours."""
    project = Path(request.project).expanduser().resolve()
    if not project.is_dir():
        raise OperationError(f"Project directory does not exist: {project}")
    web_path = project / ANSWERS_FILE
    if not web_path.is_file():
        raise OperationError(f"{project} has no {ANSWERS_FILE}: it was not generated from web-core-template.")
    if (project / NATIVE_ANSWERS_FILE).is_file() or (project / "ios").exists():
        raise OperationError(f"{project} already has an ios/ directory or a native layer; nothing was changed.")
    answers = read_answers(web_path.read_text(encoding="utf-8"))
    native_options = parse_options(NATIVE_TEMPLATE, request.native_options)
    _clean_repository(project)

    problems = [name for name in ("zod", "rest_api", "auth") if answers.get(name) != "true"]
    if answers.get("database") in (None, "none"):
        problems.append("database")
    if problems:
        raise UsageError(
            f"The native layer needs the full-stack baseline; this project lacks: {', '.join(problems)}. "
            "Create a full-stack project, or enable these features first (devkit upgrade --set ...)."
        )
    if answers.get("native_client") != "true":
        raise UsageError(
            "The web part has to serve native clients first: run `devkit upgrade PROJECT --set native_client=true`, "
            "review and commit that, then run this again. (devkit does not switch it on for you.)"
        )
    web_release = _installed_release(answers.get("_commit", ""))
    web = ResolvedTemplate(location=answers.get("_src_path", ""), ref=format_tag(web_release), mode="published", local_root=None)
    native = resolve_template(NATIVE_TEMPLATE, request.native_template, request.native_template_ref)
    ensure_options_available(NATIVE_TEMPLATE, native_options, native)
    check_pair(web, native)
    name = answers.get("app_name")
    if not name:
        raise OperationError(f"{ANSWERS_FILE} does not record app_name.")
    apply_native_layer(NATIVE_TEMPLATE, native, project, name, native_options, pretend=request.dry_run, leftover=None)
    return native


def layer_statuses(project: Path) -> list[LayerStatus]:
    project = Path(project).expanduser()
    found: list[LayerStatus] = []
    for layer, name, spec in (
        ("web", ANSWERS_FILE, get_profile("web-core").template),
        ("native", NATIVE_ANSWERS_FILE, NATIVE_TEMPLATE),
    ):
        path = project / name
        if not path.is_file():
            continue
        assert spec is not None
        answers = read_answers(path.read_text(encoding="utf-8"))
        installed = parse_release_tag(answers.get("_commit", ""))
        newest, note = None, ""
        if installed is None:
            note = f"recorded version {answers.get('_commit')!r} is not a release tag"
        else:
            if not spec.versions.contains(installed):
                note = f"outside the range this devkit supports ({spec.versions})"
            try:
                newer = [v for v in list_release_tags(answers.get("_src_path", "")) if spec.versions.contains(v)]
                newest = max(newer) if newer else None
            except Exception:
                note = (note + "; " if note else "") + "the template origin could not be read"
        found.append(LayerStatus(layer, installed, newest, note))
    return found


def pair_problem(statuses: list[LayerStatus]) -> str | None:
    """A message when the installed releases of the two layers do not belong together, else None."""
    by = {s.layer: s for s in statuses}
    if "web" in by and "native" in by and by["web"].installed and by["native"].installed:
        required = native_requirement(by["native"].installed)
        if required is not None and not required.contains(by["web"].installed):
            return (
                f"native {format_tag(by['native'].installed)} works with web {required}, but the web layer is at "
                f"{format_tag(by['web'].installed)}: the generated API client may not match the server."
            )
    return None


__all__ = ["AddNativeRequest", "LayerStatus", "add_native_layer", "layer_statuses", "pair_problem", "PROFILES"]
