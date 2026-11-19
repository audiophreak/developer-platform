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
    kind: Literal["bool", "str", "int"]
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
    answers_file: str = ".copier-answers.yml"  # where Copier records this template's answers in a project


@dataclass(frozen=True)
class Profile:
    id: str
    title: str
    available: bool
    summary: str
    template: TemplateSpec | None = None
    # Options the profile defines rather than the person choosing them. Naming a different value is refused; naming
    # the same one is allowed. They are part of what the profile IS, not features switched on behind your back.
    fixed: tuple[tuple[str, object], ...] = ()
    # Options the person must state because the choice is architectural (never defaulted by the profile).
    required: tuple[str, ...] = ()
    native: TemplateSpec | None = None  # a second template applied to the same directory (the native iOS layer)


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
            versions=VersionRange((0, 1, 0), (0, 8, 0)),
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
                Option(
                    "native_client",
                    "bool",
                    "Bearer tokens for native clients and a deterministic OpenAPI 3.1 contract of /api/v1 "
                    "(requires auth=true)",
                    default=False,
                    since=(0, 7, 0),
                    sticky=True,
                    sticky_reason=(
                        "Removing native-client support is a code change you make by hand (the bearer plugin and the "
                        "contract): a native app may depend on it. See the project's docs/native-client.md."
                    ),
                ),
            ),
        ),
    ),
}

_WEB = PROFILES["web-core"].template
assert _WEB is not None

# The native iOS layer: a second template, applied to the same directory, with its own releases and answers file.
NATIVE_TEMPLATE = TemplateSpec(
    url="https://github.com/audiophreak/native-ios-template.git",
    versions=VersionRange((0, 1, 0), (0, 2, 0)),
    node_major=0,  # not a Node template
    answers_file=".copier-answers.ios.yml",
    options=(
        Option("app_display_name", "str", "Name shown under the app icon", since=(0, 1, 0)),
        Option("bundle_identifier", "str", "Bundle identifier (reverse DNS); a placeholder default", since=(0, 1, 0)),
        Option("debug_api_port", "int", "Port of the local development server the Debug build talks to", default="3000", since=(0, 1, 0)),
        Option("release_api_host", "str", "Host the Release build talks to over https; a placeholder default", since=(0, 1, 0)),
    ),
)

# Which web releases each native release was generated against (its API contract). A pair outside this is refused:
# the generated client would not match the server. Keyed by the native release's (major, minor).
NATIVE_REQUIRES_WEB: dict[tuple[int, int], VersionRange] = {
    (0, 1): VersionRange((0, 7, 0), (0, 8, 0)),
}

# The established full-stack baseline (every application in this profile has these) and what stays a choice.
_FULL_STACK_FIXED: tuple[tuple[str, object], ...] = (("zod", True), ("rest_api", True), ("auth", True))

PROFILES["full-stack"] = Profile(
    "full-stack",
    "Full-stack Web",
    True,
    "Web Core with Zod, the REST API, a PostgreSQL or Supabase database and Better Auth (Forms optional)",
    _WEB,
    fixed=_FULL_STACK_FIXED,
    required=("database",),
)
PROFILES["native-ios"] = Profile(
    "native-ios",
    "Web + Native iOS",
    True,
    "The full-stack web application plus a native SwiftUI iOS app with a generated typed API client",
    _WEB,
    fixed=_FULL_STACK_FIXED + (("native_client", True),),
    required=("database",),
    native=NATIVE_TEMPLATE,
)


def native_requirement(native_version: Version) -> VersionRange | None:
    """The web releases a native release works with, or None for a native release this devkit does not know."""
    return NATIVE_REQUIRES_WEB.get(native_version[:2])


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
