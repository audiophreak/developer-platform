# Architecture

`developer-platform` provisions a development workstation and generates new applications from
independently versioned templates. This document records the design and the assumptions that
changed since v0.1. `usage.md` explains how to use it, `publishing.md` how to release it, and
`milestone-v0.2-repository-split.md` what the split changed and how it was verified.

## Two repositories, two version lines

| Repository                    | Owns                                                                  | Versions                 |
| ----------------------------- | --------------------------------------------------------------------- | ------------------------ |
| `developer-platform` (this)   | `devkit` CLI, workstation tooling (`Brewfile`, `doctor`), profile registry, source resolution, platform docs | `vMAJOR.MINOR.PATCH` of devkit |
| `web-core-template`           | The Web Core Copier template: `copier.yml`, `template/`, its validation, its tests, its upgrade docs | `vMAJOR.MINOR.PATCH` of the template |

Why separate: Copier upgrades a generated project by re-rendering the template at the release the
project recorded and at the one you update to, so a template must be one git repository whose tags
are its releases. Keeping the CLI in the same repository would tie every CLI change to a template
release and put non-template tags into the template's history.

Disadvantages considered, none material:

- *A contract across two repositories can drift.* Mitigated by making the dependency one-way (the
  platform declares what it supports; the template knows nothing about the platform), by moving
  every content rule into the template where Copier enforces it (nothing is mirrored), and by a
  contract test (`tests/test_integration_web_core.py`) that checks the registry against the real
  `copier.yml`.
- *Two release processes.* Only breaking template releases need a matching platform release,
  because the platform pins a supported range.
- *A heavier local loop.* `devkit new --template PATH` renders a checkout as it is on disk, and the
  template repository has its own self-contained test suite.

### The contract (`src/devkit/profiles.py`)

Each available profile carries a `TemplateSpec`:

| Field        | Meaning                                                                         |
| ------------ | ------------------------------------------------------------------------------- |
| `url`        | The published origin. Recorded verbatim in generated projects (portable).       |
| `versions`   | Half-open range of template releases this devkit supports, e.g. `>=0.1.0,<0.2.0`. |
| `node_major` | Node.js major those releases pin; `doctor` checks it.                           |
| `options`    | Template questions `--set NAME=VALUE` may set, with their type.                 |

The template must accept `app_name` and `app_description` (always sent) and every declared option.
A template release that breaks any of this (new Node major, renamed question) must bump its minor
version, and the platform widens or moves the range in the same change. Plain
`copier update` ignores the range (it takes the newest tag), so upgrade documentation always pins
`--vcs-ref`; a test records that behaviour.

### How a template is chosen (`src/devkit/sources.py`)

- **Published mode (default):** the profile's `url`, at the newest tag `vMAJOR.MINOR.PATCH` inside
  the supported range (found with `git ls-remote --tags`). Pre-release and other tags are ignored.
  `--template-ref vX.Y.Z` picks a specific supported release. Nothing is rendered from a branch or
  an untagged commit. The project records the URL and the tag.
- **Local mode (`--template PATH`):** a checkout on this machine, rendered as it is on disk
  (working tree included) unless `--template-ref` names a git ref. For developing the template;
  works with no published repository. The project records a home-relative path (`~/...`), so it is
  not portable, and `devkit` says so.
- `--template URL` swaps the origin but keeps published-mode rules. A path to a *bare* repository
  counts as an origin, not a checkout.
- An unreachable origin, an origin with no supported release, a missing tag and a failed
  generation each stop with a specific message and leave nothing behind. Credentials in URLs are
  redacted from messages, and git never prompts.

## Components

| Concern                 | Tool                                       | Status                                         |
| ----------------------- | ------------------------------------------ | ---------------------------------------------- |
| Workstation packages    | Homebrew `Brewfile`                        | Provided; `doctor` only checks it              |
| Per-project runtimes    | `.nvmrc` + `engines` (Node), `uv` (Python) | In use; mise evaluated, not adopted            |
| Application templates   | Copier, one repository per template        | `web-core-template`                            |
| Command line            | `devkit` (Python, `argparse`)              | `doctor`, `new`, `new --dry-run`, `--set`, `--template` |
| Repository creation     | GitHub CLI                                 | Later milestone; `doctor` checks auth          |
| Continuous integration  | GitHub Actions                             | In generated projects; none for these repos yet |
| AI development guidance | `AGENTS.md` + `CLAUDE.md`                  | In generated projects and in both repositories |

## Why Copier, and its drawbacks

Copier provides parameterised templates, versioned releases (git tags), `copier update` with a
three-way merge, and a Python API that `devkit` wraps. Alternatives considered: `create-next-app`
plus scripts (no upgrades), Cookiecutter (no upgrades), GitHub template repositories (no
parameters or upgrades), Yeoman/Plop (JavaScript tooling for a Python-led platform), Nx/Turborepo
generators (assume a monorepo).

Drawbacks, each verified or mitigated:

1. **Updates are git merges, so they conflict.** Needs a clean git working tree and merges line by
   line; `package.json`, `globals.css` and the lockfile conflict most. Conflicts are written inline
   and the command exits 0, so users must search for markers (a test confirms nothing is silently
   lost). Documented procedure: resolve, run `npm install`, run `npm run check`.
2. **Plain `copier update` takes the newest tag**, even a breaking one outside the supported range.
   Upgrade docs pin `--vcs-ref`.
3. **Template state matters silently.** Verified: once a repository has a tag, Copier renders the
   latest tag and ignores uncommitted edits unless given an explicit ref. `devkit` always passes
   one (`HEAD` in local mode, a tag in published mode).
4. **Copier records the template location verbatim.** Published mode records the URL (portable);
   local mode records `~/path` (no user name, but local). Copier's `Worker` class and internals
   are marked internal-only, so `devkit` uses only `run_copy` and treats its error text for
   validation failures (`Validation error for question ...`) as a pinned-version contract with a
   test.
5. **Code execution.** `_tasks`, `_migrations` and Jinja extensions run code and require `--trust`.
   The template uses none (a test enforces it) and `devkit` passes `unsafe=False` and empty user
   settings.
6. **Jinja inside JSON, TSX, YAML and Markdown is awkward** (escaping, `${{ }}` in Actions,
   Prettier). Only files needing substitution carry `.jinja`; app identity lives in
   `src/lib/app-info.json`; descriptions are restricted to a safe ASCII set; end-to-end tests run
   the full gate on apps with awkward answers.
7. **Lockfiles do not compose.** A static lockfile works for Web Core; feature combinations will
   need one generated at creation time (see "Dependency pins").

## mise evaluation

mise could manage Node, Python and other tools per project. Not adopted: Node is pinned in
`.nvmrc` and `engines` (read by fnm, nvm, mise and `actions/setup-node`), Python is handled by
`uv`, and the workstation already has `fnm` and `uv`. Adding mise adds a shell hook and a second
source of truth. Revisit when a profile needs a third runtime or CLI (for example the Supabase CLI)
that Homebrew cannot pin per project. `doctor` reports mise as optional.

## Profiles and features (design; only Web Core exists)

| Profile      | Contents                                                                | Status   |
| ------------ | ----------------------------------------------------------------------- | -------- |
| `web-core`   | Next.js 16, React 19, strict TS, Tailwind v4, shadcn/ui, ESLint, Prettier, Vitest, CI, AI instructions | **Available** (`web-core-template`) |
| `full-stack` | Web Core plus a server layer: services, data access, validation, optional database, auth, REST API | Reserved |
| `native-ios` | Full-stack plus a native iOS (SwiftUI) client, OpenAPI contract, macOS CI job | Reserved |

Reserved profiles are rejected with an explicit message so later milestones do not change the CLI.

**Composition across templates (unresolved).** Copier has no template inheritance. The promising
approach, not yet prototyped, is layering: apply `web-core-template`, then a separate add-on
template onto the same directory with its own answers file (Copier supports several answers files
per project), each independently versioned and upgraded. The alternative, one template with a
`profile` question and conditional files, keeps one version line but makes every profile change a
release of everything. This needs a decision and a prototype before the full-stack milestone.

Planned optional features:

| Feature           | Options                       | Requires                    | Allowed in             |
| ----------------- | ----------------------------- | --------------------------- | ---------------------- |
| `zod`             |                               |                             | all profiles           |
| `forms`           |                               | `zod`                       | all profiles           |
| `rest-api`        | versioned `/api/v1`           | `zod`                       | full-stack, native-ios |
| `docker-services` | Compose services              |                             | full-stack, native-ios |
| `database`        | `supabase` or `postgres`      | `zod`, `docker-services`    | full-stack, native-ios |
| `auth`            | `supabase-auth` or `authjs`   | `database`, `zod`           | full-stack, native-ios |
| `deployment`      | `none`, `vercel`, `container` |                             | all profiles           |

`native-ios` implies `rest-api` and `auth`. Incompatible: `auth=supabase-auth` without
`database=supabase`; `deployment=vercel` with `database=postgres` (local Postgres is unreachable
from Vercel).

**Enforcement.** Rules about answers belong with the template that owns the questions: Copier
`when:` conditions and validators in that template's `copier.yml` reject invalid combinations for
every caller, and that template's tests enumerate the combinations. The platform's profile
registry declares which options exist and their types, so `--set` rejects unknown options before
any network access, and the platform adds only cross-template rules (for example which layers a
profile applies). Failures name the features involved and exit 2, nothing is written, and
`--dry-run` shows the resolved plan.

## Dependency pins

Generated projects use exact versions and a committed lockfile. Web Core ships a static, verified
lockfile (`web-core-template/docs/maintaining.md` explains refreshing it). For profiles with
features, versions will live in one catalogue and the lockfile will be generated at creation with
`npm install --before=<two weeks ago>`, keeping the two-week release-age rule. Python dependencies
in both repositories are exact-pinned with `uv.lock` and resolved with an `exclude-newer` cutoff.

## Next.js configuration review

The template inherits the scaffold's `next.config.ts`. Reviewed against the bundled Next.js 16.4.5
docs:

| Setting                                  | Decision                                                                 |
| ---------------------------------------- | ------------------------------------------------------------------------ |
| `cacheComponents: true`                  | **Now optional** (`cache_components`, default on). It changes the data-fetching model (dynamic by default, caching opt-in with `use cache`), requires the Node.js runtime and rejects the `runtime` route segment config. It is the scaffold's own default and Next.js intends to make it universal, so the default stays on. |
| `partialPrefetching: true`               | **Tied to the same switch.** The docs say it requires `cacheComponents` (config validation throws otherwise) and recommend setting both; so it is never emitted alone. |
| `turbopack.rules` for `*.css`            | Kept, unconditional: it wires Tailwind in this scaffold (no PostCSS config). Not in the docs; comes from `create-next-app`. |
| `engines.node: ">=26 <27"`               | Kept. The upper bound is deliberate: pins were verified on Node 26; a new major should be a reviewed template release. |
| `next/font/google` (Geist) in the layout | Kept; note it needs network at build time. A later option could swap to local fonts. |
| `tsconfig` `allowJs: true`               | Kept (scaffold default); harmless, could become strict-TypeScript-only later. |

## Security posture

- `doctor` is read-only and never prints identity values. `new` never overwrites: any existing
  path at the destination (directory, empty directory, file, symlink) is refused, as are
  destinations inside either checkout. Dry run writes nothing.
- The CLI builds filesystem paths only from a validated single path segment and runs git with
  argument lists, no prompts and no optional locks.
- Generation runs with `unsafe=False`, ignores user-level Copier settings, and the template
  contains no tasks, migrations or extensions.
- Generated projects contain no secrets, identities or machine paths (the template repository's
  tests scan every generated file). GitHub Actions use read-only permissions,
  `persist-credentials: false` and full-commit-SHA pins.
- Messages redact URL credentials. `devkit` never reads, stores or passes credentials: git runs with
  prompting disabled and uses whatever credential helper is configured. The template and the
  platform repositories are private; see `publishing.md` for access and its limitations.

## Corrections to earlier assumptions

1. **Reserved npm names removed.** v0.1 rejected app names equal to packages in the lockfile on the
   claim that npm could not install them. Tested against npm 11: a project named `next` or
   `debug` passes `npm ci`, `npm run check` and a same-version `npm install` of the package it is
   named after. (An install that changes that package's version was not tested.) The rule was
   unjustified and is gone.
2. **One repository became two** (above), and answer validation moved into the template.
3. **The recorded template location** is now the published URL in the normal case; the
   home-relative path is confined to local development mode.
4. **The shadcn/ui baseline is now merged** into the reference application (PR #2, commit
   `f244594`). The template was first derived from an uncommitted working tree; it has since
   been compared against the merged commit and differs only by intentional substitutions
   (`web-core-template/docs/provenance.md`).

## Open decisions

1. Published as two **private** repositories (`publishing.md`); revisit visibility if others need to
   use the platform.
2. How profiles compose across templates (layering or one template).
3. A `devkit upgrade` command that enforces the supported range (plain `copier update` does not).
