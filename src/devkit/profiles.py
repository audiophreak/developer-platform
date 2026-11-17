"""Technology profiles and the template release each one is built from.

Boundary: the platform (this package) declares which versions of a template it supports and
which options it exposes. A template never knows about the platform. A template release that
breaks that contract (new Node major, renamed options) must bump the minor/major version so the
supported range here changes with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .errors import UsageError

DEFAULT_PROFILE = "web-core"

Version = tuple[int, int, int]


@dataclass(frozen=True)
class VersionRange:
    minimum: Version
    maximum_exclusive: Version

    def contains(self, version: Version) -> bool:
        return self.minimum <= version < self.maximum_exclusive

    def __str__(self) -> str:
        low = ".".join(map(str, self.minimum))
        high = ".".join(map(str, self.maximum_exclusive))
        return f">={low},<{high}"


@dataclass(frozen=True)
class Option:
    """A template question the CLI may set with `--set NAME=VALUE`."""

    name: str
    kind: Literal["bool", "str"]
    help: str


@dataclass(frozen=True)
class TemplateSpec:
    url: str  # published origin; recorded in generated projects
    versions: VersionRange  # template releases this devkit supports
    node_major: int  # Node.js major those releases pin (checked by `doctor`)
    options: tuple[Option, ...] = ()


@dataclass(frozen=True)
class Profile:
    id: str
    title: str
    available: bool
    summary: str
    template: TemplateSpec | None = None


PROFILES: dict[str, Profile] = {
    "web-core": Profile(
        "web-core",
        "Web Core",
        True,
        "Next.js, strict TypeScript, Tailwind, shadcn/ui, ESLint, Prettier, Vitest, CI",
        TemplateSpec(
            # Assumes the template repository is published under the same GitHub account as
            # the reference application. Confirm or change before the first release.
            url="https://github.com/audiophreak/web-core-template.git",
            versions=VersionRange((0, 1, 0), (0, 2, 0)),
            node_major=26,
            options=(
                Option(
                    "cache_components",
                    "bool",
                    "Next.js Cache Components with Partial Prefetching (default: true)",
                ),
            ),
        ),
    ),
    "full-stack": Profile(
        "full-stack",
        "Full-stack Web",
        False,
        "Web Core plus data, validation, auth and API features (planned)",
    ),
    "native-ios": Profile(
        "native-ios",
        "Web + Native iOS",
        False,
        "Full-stack Web plus a native iOS client (planned)",
    ),
}


class ProfileError(UsageError):
    """The requested profile is unknown or not implemented yet."""


def get_profile(profile_id: str) -> Profile:
    profile = PROFILES.get(profile_id)
    if profile is None:
        known = ", ".join(sorted(PROFILES))
        raise ProfileError(f"Unknown profile {profile_id!r}. Known profiles: {known}.")
    if not profile.available or profile.template is None:
        raise ProfileError(
            f"Profile {profile.id!r} ({profile.title}) is reserved for a later milestone "
            f"and is not implemented yet. Available now: {DEFAULT_PROFILE}."
        )
    return profile
