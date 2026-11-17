"""Checks the CLI itself owns.

Rules about the application's *content* (name format, description, option values) live in the
template's `copier.yml`, with the template version that needs them, and are enforced by Copier.
The CLI only guarantees that what it builds a filesystem path from is a single safe path
segment, and that `--set` options are ones the profile declares.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from .errors import UsageError
from .profiles import TemplateSpec
from .sources import ResolvedTemplate, local_question_names, release_version

SAFE_PATH_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
RESERVED_ANSWERS = frozenset({"app_name", "app_description"})
_TRUE = {"true", "yes", "1", "on"}
_FALSE = {"false", "no", "0", "off"}


def validate_destination_name(name: str) -> str:
    if not SAFE_PATH_SEGMENT.fullmatch(name):
        raise UsageError(
            f"Invalid name {name!r}: it becomes a directory name, so use 1-100 letters, digits, "
            "dots, hyphens or underscores, starting with a letter or digit."
        )
    return name


def parse_options(spec: TemplateSpec, pairs: Sequence[str]) -> dict[str, object]:
    """Turn repeated `NAME=VALUE` arguments into typed answers for the profile's options."""
    known = {option.name: option for option in spec.options}
    answers: dict[str, object] = {}
    for pair in pairs:
        name, separator, raw = pair.partition("=")
        if not separator or not name:
            raise UsageError(f"Invalid --set {pair!r}: use NAME=VALUE.")
        if name in RESERVED_ANSWERS:
            raise UsageError(f"--set cannot change {name!r}; use the dedicated argument or option.")
        option = known.get(name)
        if option is None:
            allowed = ", ".join(sorted(known)) or "none"
            raise UsageError(f"Unknown option {name!r} for this profile. Available options: {allowed}.")
        if name in answers:
            raise UsageError(f"Option {name!r} was given more than once.")
        if option.kind == "bool":
            lowered = raw.strip().lower()
            if lowered in _TRUE:
                answers[name] = True
            elif lowered in _FALSE:
                answers[name] = False
            else:
                raise UsageError(f"Option {name!r} is true/false; got {raw!r}.")
        else:
            answers[name] = raw
    return answers


def ensure_options_available(spec: TemplateSpec, options: dict[str, object], template: ResolvedTemplate) -> None:
    """Refuse an option the selected template release does not have.

    Copier silently ignores an answer for a question that does not exist, so without this check
    `--set zod=true` against a release without the feature would generate a project that quietly
    lacks it. A release tag is judged by the registry (`Option.since`); a local checkout is judged
    by the questions in its own copier.yml at the ref being rendered.
    """
    if not options:
        return
    version = release_version(template)
    questions = None
    if version is None and template.local_root is not None:
        questions = local_question_names(template.local_root, template.ref)
    for option in spec.options:
        if option.name not in options:
            continue
        if version is not None and version < option.since:
            needed = "v" + ".".join(map(str, option.since))
            chosen = "v" + ".".join(map(str, version))
            raise UsageError(
                f"Option {option.name!r} needs template {needed} or newer, but release {chosen} is selected. "
                "Choose a newer release (omit --template-ref) or drop the option."
            )
        if questions is not None and option.name not in questions:
            raise UsageError(
                f"Option {option.name!r} is not a question of the template at {template.ref or 'HEAD'} "
                f"({template.location}), so it would be silently ignored."
            )
