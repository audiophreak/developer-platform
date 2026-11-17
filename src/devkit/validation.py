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
