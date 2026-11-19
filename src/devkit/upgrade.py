"""Upgrade an existing project to a newer template release (`devkit upgrade`).

Safety rules, in the order they are enforced:

1. The project must be a git repository root with a clean working tree (nothing modified, nothing
   untracked), so every user change is already committed and recoverable.
2. The project's recorded release (`_commit` in `.copier-answers.yml`) must be a plain release tag
   inside the range this devkit supports; the target must be newer, inside that range and
   published. Anything else is refused before the project is touched.
3. Existing answers (feature selections) are kept: Copier reuses recorded answers, and features the
   new release introduces take their default. `--set` changes an option deliberately.
4. `--dry-run` shows the plan and runs Copier's preview, which writes nothing.
5. Copier merges the new release into the user's files (a three-way merge). Conflicts are left as
   inline markers; nothing is overwritten or deleted, and the command reports the files.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import copier
from copier import Settings
from copier.errors import DirtyLocalWarning

from .errors import OperationError, UpgradeConflictError, UsageError
from .generate import verify_options_recorded
from .gitutil import git, redact
from .profiles import DEFAULT_PROFILE, NATIVE_TEMPLATE, Version, get_profile, native_requirement
from .sources import ResolvedTemplate, format_tag, list_release_tags, parse_release_tag
from .validation import ensure_options_available, parse_options

ANSWERS_FILE = ".copier-answers.yml"
NATIVE_ANSWERS_FILE = NATIVE_TEMPLATE.answers_file
_ANSWER_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*?)[ \t]*$")
_DEVELOPMENT_COMMIT = re.compile(r"^v\d+\.\d+\.\d+-\d+-g[0-9a-f]+$")
_CONFLICT_START = re.compile(r"^<{7} ", re.MULTILINE)
_CONFLICT_END = re.compile(r"^>{7} ", re.MULTILINE)


@dataclass(frozen=True)
class UpgradeRequest:
    project: Path
    to: str | None = None
    options: tuple[str, ...] = ()
    profile: str = DEFAULT_PROFILE
    dry_run: bool = False
    # A project made by the native-ios profile has two layers with their own releases and answers files; each is
    # upgraded on its own (and committed on its own). "auto" is the web layer, and refuses to guess when there are two.
    layer: str = "auto"


@dataclass(frozen=True)
class UpgradePlan:
    project: Path
    source: str
    installed: Version
    target: Version | None  # None: already up to date
    preserved: dict[str, str]
    options: dict[str, object]
    warnings: tuple[str, ...] = ()
    layer: str = "web"
    answers_file: str = ANSWERS_FILE
    pending: tuple[str, ...] = ()  # other layers that are not up to date: the project is not fully upgraded

    @property
    def crosses_minor(self) -> bool:
        return self.target is not None and self.target[:2] != self.installed[:2]


@dataclass(frozen=True)
class UpgradeResult:
    plan: UpgradePlan
    changed: bool
    dry_run: bool
    conflicts: tuple[str, ...] = field(default_factory=tuple)


def _canonical(value: object) -> str | None:
    """Answers are recorded as text (`true`) and options arrive typed (`True`): compare them as lower-case text."""
    return None if value is None else str(value).lower()


def read_answers(text: str) -> dict[str, str]:
    """The flat `key: value` lines Copier writes. Quotes around a value are removed."""
    answers: dict[str, str] = {}
    for line in text.splitlines():
        match = _ANSWER_LINE.match(line)
        if match:
            value = match.group(2)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            answers[match.group(1)] = value
    return answers


def _clean_repository(project: Path) -> None:
    top = git("rev-parse", "--show-toplevel", cwd=project)
    if not (top and top.returncode == 0 and Path(top.stdout.strip()).resolve() == project.resolve()):
        raise OperationError(
            f"{project} is not the root of a git repository. Copier can only update a committed project; "
            "run `git init`, commit it, and retry."
        )
    status = git("status", "--porcelain", "-uall", cwd=project)
    if status is None or status.returncode != 0:
        raise OperationError(f"Cannot read the git status of {project}.")
    if status.stdout.strip():
        raise OperationError(
            f"{project} has uncommitted changes (modified or untracked files). Commit or stash them first, "
            "so the upgrade can never mix with your work. Nothing was changed."
        )


def _installed_release(commit: str) -> Version:
    version = parse_release_tag(commit)
    if version is not None:
        return version
    if _DEVELOPMENT_COMMIT.match(commit):
        raise OperationError(
            f"The project was generated from commits after a release ({commit}), i.e. an unreleased template; "
            "devkit cannot tell which release it matches. Regenerate it from a release to upgrade it."
        )
    raise OperationError(
        f"The project's recorded template version {commit!r} is not a release tag (vX.Y.Z), so devkit cannot "
        "decide what to upgrade to."
    )


def _resolve_layer(request: UpgradeRequest, project: Path):
    """(layer name, template spec) for this request; refuses to guess in a project with two layers."""
    if request.layer not in ("auto", "web", "native"):
        raise UsageError(f"--layer must be web or native, not {request.layer!r}.")
    two_layers = (project / NATIVE_ANSWERS_FILE).is_file()
    layer = request.layer
    if layer == "auto":
        if two_layers:
            raise UsageError(
                f"{project} has a web layer and a native iOS layer, each with its own releases. Choose one: "
                "--layer web or --layer native (upgrade and commit them one at a time; `devkit status` shows both)."
            )
        layer = "web"
    if layer == "native":
        if not two_layers:
            raise UsageError(f"{project} has no native iOS layer ({NATIVE_ANSWERS_FILE}).")
        return "native", NATIVE_TEMPLATE
    spec = get_profile(request.profile).template
    assert spec is not None
    return "web", spec


def _pair_problems(layer: str, project: Path, target: Version | None) -> None:
    """Refuse an upgrade that would leave the two layers on releases that do not belong together."""
    if target is None:
        return
    if layer == "web" and (project / NATIVE_ANSWERS_FILE).is_file():
        native = _installed_release(read_answers((project / NATIVE_ANSWERS_FILE).read_text(encoding="utf-8")).get("_commit", ""))
        required = native_requirement(native)
        if required is not None and not required.contains(target):
            raise UsageError(
                f"The native layer ({format_tag(native)}) works with web-core-template {required}; upgrading the web "
                f"layer to {format_tag(target)} would break its generated API client. Upgrade the native layer first "
                "(once a release for the new web contract exists), or stay on a web release in that range."
            )
    if layer == "native" and (project / ANSWERS_FILE).is_file():
        web = _installed_release(read_answers((project / ANSWERS_FILE).read_text(encoding="utf-8")).get("_commit", ""))
        required = native_requirement(target)
        if required is not None and not required.contains(web):
            raise UsageError(
                f"native-ios-template {format_tag(target)} needs web-core-template {required}, but the web layer is at "
                f"{format_tag(web)}. Upgrade the web layer first."
            )


def plan_upgrade(request: UpgradeRequest) -> UpgradePlan:
    project = Path(request.project).expanduser()
    layer, spec = _resolve_layer(request, project) if project.is_dir() else ("web", get_profile(request.profile).template)
    assert spec is not None
    answers_name = spec.answers_file
    supported = spec.versions
    options = parse_options(spec, request.options)
    wanted: Version | None = None
    if request.to is not None:  # argument problems come first: they need no look at the project
        wanted = parse_release_tag(request.to)
        if wanted is None:
            raise UsageError(f"--to {request.to!r} is not a release tag (vMAJOR.MINOR.PATCH).")
        if not supported.contains(wanted):
            raise UsageError(f"{request.to} is outside the range this devkit supports ({supported}).")

    if not project.is_dir():
        raise OperationError(f"Project directory does not exist: {project}")
    answers_path = project / answers_name
    if not answers_path.is_file():
        raise OperationError(f"{project} has no {answers_name}: it was not generated from a Copier template.")
    answers = read_answers(answers_path.read_text(encoding="utf-8"))
    source, commit = answers.get("_src_path"), answers.get("_commit")
    if not source or not commit:
        raise OperationError(f"{answers_name} does not record the template source and version (_src_path, _commit).")

    _clean_repository(project)
    installed = _installed_release(commit)
    if installed < supported.minimum:
        raise UsageError(
            f"The project is at {format_tag(installed)}, older than the oldest release this devkit supports "
            f"({format_tag(supported.minimum)}). Use a devkit that supports it, or regenerate the project."
        )
    if not supported.contains(installed):
        raise UsageError(
            f"The project is at {format_tag(installed)}, newer than this devkit supports ({supported}). Use a newer devkit."
        )

    for option in spec.options:
        recorded, requested = _canonical(answers.get(option.name)), _canonical(options.get(option.name))
        if option.sticky and requested is not None and recorded not in (None, _canonical(option.default)) and requested != recorded:
            reason = option.sticky_reason.format(recorded=repr(recorded), requested=repr(requested))
            raise UsageError(
                f"{option.name} is {recorded!r} in this project; changing it to {requested!r} is not an upgrade. {reason}"
            )

    listing = source if not source.startswith("~") else str(Path(source).expanduser())
    available = [v for v in list_release_tags(listing) if supported.contains(v)]
    if wanted is not None:
        if wanted not in available:
            raise OperationError(f"Release {request.to} does not exist at {redact(source)}.")
        if wanted < installed:
            raise UsageError(f"Refusing to downgrade from {format_tag(installed)} to {request.to}.")
        target: Version | None = wanted
    else:
        newer = [v for v in available if v > installed]
        target = max(newer) if newer else (installed if options else None)  # options re-render the release
    if target == installed and not options:
        target = None  # nothing to do

    _pair_problems(layer, project, target)
    notes: list[str] = []
    if source.startswith(("~", "/", ".")):
        notes.append("The project's template source is a local path (a development origin), not a published URL.")
    elif redact(source) != spec.url:
        notes.append(f"The recorded origin differs from the profile's published origin ({spec.url}).")
    if target is not None and options:
        ensure_options_available(
            spec, options, ResolvedTemplate(location=source, ref=format_tag(target), mode="published", local_root=None)
        )
    preserved = {k: v for k, v in answers.items() if not k.startswith("_")}
    return UpgradePlan(project, source, installed, target, preserved, options, tuple(notes), layer, answers_name, _other_layer_pending(layer, project))


def _other_layer_pending(layer: str, project: Path) -> tuple[str, ...]:
    """The other layer, when it has a newer supported release: the project is only fully upgraded when both are."""
    if layer == "web" and (project / NATIVE_ANSWERS_FILE).is_file():
        other, name, spec = "native", NATIVE_ANSWERS_FILE, NATIVE_TEMPLATE
    elif layer == "native" and (project / ANSWERS_FILE).is_file():
        other, name, spec = "web", ANSWERS_FILE, get_profile(DEFAULT_PROFILE).template
    else:
        return ()
    assert spec is not None
    answers = read_answers((project / name).read_text(encoding="utf-8"))
    source, commit = answers.get("_src_path"), answers.get("_commit")
    installed = parse_release_tag(commit or "")
    if not source or installed is None:
        return ()
    try:
        newer = [v for v in list_release_tags(source) if spec.versions.contains(v) and v > installed]
    except Exception:  # the other origin may be unreachable; the plan of this layer stands
        return ()
    return (f"{other} layer: {format_tag(installed)} -> {format_tag(max(newer))} available",) if newer else ()


def _conflicted_files(project: Path) -> list[str]:
    status = git("status", "--porcelain", "-z", "-uall", cwd=project)
    if status is None or status.returncode != 0:
        return []
    entries = status.stdout.split("\0")
    found, skip = [], False
    for entry in entries:
        if skip:
            skip = False
            continue
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if code[0] in "RC":
            skip = True  # the next entry is the original name
        try:
            text = (project / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _CONFLICT_START.search(text) and _CONFLICT_END.search(text):
            found.append(path)
    return sorted(found)


def upgrade_project(
    request: UpgradeRequest, on_plan: Callable[[UpgradePlan], None] | None = None
) -> UpgradeResult:
    plan = plan_upgrade(request)
    if on_plan is not None:
        on_plan(plan)
    if plan.target is None:
        return UpgradeResult(plan, changed=False, dry_run=request.dry_run)

    import warnings

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DirtyLocalWarning)
            copier.run_update(
                dst_path=plan.project,
                data=plan.options or None,
                answers_file=Path(plan.answers_file),
                vcs_ref=format_tag(plan.target),
                settings=Settings(),  # ignore any user-level Copier settings
                defaults=True,
                skip_answered=True,  # keep recorded answers: feature selections survive
                overwrite=True,
                conflict="inline",  # leave markers; never write .rej files or discard anything
                pretend=request.dry_run,
                unsafe=False,
                quiet=False,
                cleanup_on_error=False,  # an upgrade never removes anything on failure
            )
    except ValueError as exc:
        if str(exc).startswith(("Validation error", "Invalid choice")):
            raise UsageError(str(exc)) from exc
        raise OperationError(f"Upgrade failed: {exc}. Your committed work is untouched.") from exc
    except Exception as exc:
        raise OperationError(f"Upgrade failed: {exc}. Your committed work is untouched.") from exc

    if request.dry_run:
        return UpgradeResult(plan, changed=False, dry_run=True)

    answers = read_answers((plan.project / plan.answers_file).read_text(encoding="utf-8"))
    if answers.get("_commit") != format_tag(plan.target):
        raise OperationError(
            f"Copier finished but the recorded version is {answers.get('_commit')!r}, not {format_tag(plan.target)}. "
            f"Review {plan.project} with `git status` and `git diff`."
        )
    verify_options_recorded(plan.project, plan.options, plan.answers_file)
    conflicts = _conflicted_files(plan.project)
    if conflicts:
        raise UpgradeConflictError(
            f"Upgraded to {format_tag(plan.target)} with merge conflicts in: {', '.join(conflicts)}. "
            "Nothing was discarded: both sides are kept between <<<<<<< and >>>>>>> markers. Edit those "
            "files, then `git add` and commit; `git diff` shows everything that changed."
        )
    return UpgradeResult(plan, changed=True, dry_run=False)
