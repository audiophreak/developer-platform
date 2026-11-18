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
    default: bool | str | None = None  # the template's default; a contract test keeps them equal
    since: Version = (0, 1, 0)  # first template release that has this question
    choices: tuple[str, ...] = ()  # the closed set of values of a text option (the template validates it too)
    sticky: bool = False  # once set to a value other than the default, `devkit upgrade` will not change it
    sticky_reason: str = ""  # why, shown when `upgrade` refuses; may use {recorded} and {requested}


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
            versions=VersionRange((0, 1, 0), (0, 7, 0)),
            node_major=26,
            options=(
                Option(
                    "cache_components",
                    "bool",
                    "Next.js Cache Components with Partial Prefetching",
                    default=True,
                    since=(0, 1, 0),
                ),
                Option(
                    "zod",
                    "bool",
                    "Zod schema validation with a shared schema module (src/lib/schemas)",
                    default=False,
                    since=(0, 2, 0),
                ),
                Option(
                    "forms",
                    "bool",
                    "React Hook Form with the Zod resolver and an example form (requires zod=true)",
                    default=False,
                    since=(0, 3, 0),
                ),
                Option(
                    "rest_api",
                    "bool",
                    "Versioned REST API v1 with RFC 9457 errors (requires zod=true)",
                    default=False,
                    since=(0, 4, 0),
                ),
                Option(
                    "database",
                    "str",
                    "Local PostgreSQL with SQL migrations and a server-only data layer: postgres (Docker) or "
                    "supabase (local Supabase stack); requires zod=true",
                    default="none",
                    since=(0, 5, 0),
                    choices=("none", "postgres", "supabase"),
                    sticky=True,
                    sticky_reason=(
                        "It swaps the tooling under existing data, and moving data between providers is not automated. "
                        "Keep {recorded}, or generate a new project with {requested} and move your data deliberately "
                        "(see the project's docs/database.md)."
                    ),
                ),
                Option(
                    "auth",
                    "bool",
                    "Better Auth email/password authentication on either database provider, with a least-privilege "
                    "runtime role, owner-scoped data and a protected API (requires zod=true, rest_api=true and "
                    "database=postgres|supabase)",
                    default=False,
                    since=(0, 6, 0),
                    sticky=True,
                    sticky_reason=(
                        "Removing authentication is not automated: it would orphan accounts, sessions and the "
                        "ownership of data, and the migrations and the data need a decision of yours. Keep it, or "
                        "follow the manual steps in the project's docs/auth.md."
                    ),
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
