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
| `versions`   | Half-open range of template releases this devkit supports, e.g. `>=0.1.0,<0.7.0`. |
| `node_major` | Node.js major those releases pin; `doctor` checks it.                           |
| `options`    | Template questions `--set NAME=VALUE` may set: type, default, `since` (the first release that has it), optionally a closed set of `choices`, and `sticky` with a `sticky_reason` (an option such as the database provider or `auth` that `upgrade` will not change once it is set). |

The template must accept `app_name` and `app_description` (always sent) and every declared option
from its `since` release on. A template release that breaks any of this (new Node major, renamed
question) must bump its minor version, and the platform widens or moves the range in the same
change. The range may span several template lines: devkit 0.7.0 supports `>=0.1.0,<0.7.0`, and an
option newer than the selected release (`zod` needs 0.2.0, `forms` 0.3.0, `rest_api` 0.4.0, `database` 0.5.0, `auth` 0.6.0) is refused up front, because Copier
silently ignores an answer for a question that does not exist. After a real generation `devkit`
also verifies each requested option was recorded in the answers file.

`devkit upgrade` applies the same range to existing projects. Plain `copier update` ignores it (it
takes the newest tag), so direct use always pins `--vcs-ref`; a test records that behaviour.

**Compatibility is tested offline.** `tests/contracts/web-core/<version>.json` snapshots each
supported release's question contract (captured from the release tag by `tools/capture_contract.py`);
`tests/test_contract_snapshots.py` checks the registry against every snapshot with no network or
credentials, so CI covers it. The live check that a snapshot still equals the real template is the
release gate (`pytest -m integration`, run where the template is checked out). Details and the
alternatives considered: `release-strategy.md`, section 6.

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
| `full-stack` | Web Core with Zod, REST API, a PostgreSQL or Supabase database (chosen explicitly) and Better Auth; Forms optional | Available (devkit 0.8.0) |
| `native-ios` | Full-stack plus the native iOS layer: a second template (`native-ios-template`) applied to the same directory, with its own answers file and releases | Available (devkit 0.8.0) |

Reserved profiles are rejected with an explicit message so later milestones do not change the CLI.

**Optional features.** Within a profile, optional features are boolean Copier questions in the
template (`zod`, `forms`, `rest_api`, `database` and `auth` exist; the rest are planned). How they are represented, enforced, locked,
recorded and upgraded is decided in `feature-composition.md`; the roadmap, dependency relationships
and trust boundaries for the planned ones are in `full-stack-plan.md`.

**Composition across templates (unresolved).** Copier has no template inheritance. A feature with
its own toolchain or release cadence (native iOS) should be a separate add-on template applied to
the same directory with its own answers file, each independently versioned. This is a hypothesis
that needs a prototype before that increment (`feature-composition.md`, section 2).

## Dependency pins

Generated projects use exact versions and a committed lockfile for **every supported
configuration**: the template keeps one complete lockfile per distinct set of npm dependencies
(`web-core-template/locks/`), generated from the base lock by a maintainer tool, verified by tests
and selected at generation by a computed key. Nothing is resolved at generation
(`feature-composition.md`, section 4; `web-core-template/docs/features.md`). Python dependencies in
both repositories are exact-pinned with `uv.lock` and resolved with an `exclude-newer` cutoff.

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
3. Whether to teach `devkit upgrade` to apply a chain of releases (today it goes to one target).

## Decision: Better Auth on PostgreSQL for both database providers

Authentication (`auth`, template 0.6.0, devkit 0.7.0) uses **Better Auth, directly on PostgreSQL, for both
`database=postgres` and `database=supabase`**. It does not use Supabase Auth, and the local Supabase stack keeps
its Auth service disabled.

- **One architecture, not two.** The data layer is provider-independent (`pg`, plain SQL migrations, a
  repository that does not know the provider), and Better Auth supports PostgreSQL directly, so authentication
  can be provider-independent too. Supabase remains a PostgreSQL and local-services provider. Supporting Supabase
  Auth beside another system would mean two session mechanisms, two authorization models and two sets of
  behaviour to keep equivalent, and application code that must know which one it runs on.
- **Authorization is PostgreSQL's, not the provider's.** Ownership is enforced by row level security that reads a
  user id the server sets for one transaction, with an application role that cannot bypass it. That works on any
  PostgreSQL, so the same migrations, repository and tests run on both providers; tests run the same scenario on
  both and require identical outcomes.
- **The schema stays in the one migration history.** Better Auth's tables come from its own schema tooling,
  reviewed and committed as SQL in the same `supabase/migrations/` sequence; nothing alters the schema at run time,
  and a test fails if a Better Auth version needs more.
- **Consequences.** There is no `auth=supabase-auth`; the Supabase Data API exposes neither the application's
  schema nor the authentication schema; the roadmap's earlier idea that `database=supabase` would provide auth is
  withdrawn. A future provider only has to be PostgreSQL to inherit the whole model.
- **Boundaries.** The prerequisites (`zod`, `rest_api`, a `database`) are the template's rules, enforced by its
  validator. devkit only knows the option, the release that introduced it and that an established `auth` is not
  undone by `upgrade` (a sticky option, like the provider). The generated project says plainly what remains the
  deployer's responsibility before public use.
