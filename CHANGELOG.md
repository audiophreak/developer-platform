# Changelog

devkit versions are git tags (`vMAJOR.MINOR.PATCH`), independent of template versions.

## 0.7.0

Adds the Web Core `auth` option and widens the supported template range to `>=0.1.0,<0.7.0` (template 0.1.x
to 0.6.x). No dependency changed.

- New option `--set auth=true|false` for `web-core` (default `false`; first available in template 0.6.0):
  Better Auth email/password authentication, a least-privilege `app_runtime` database role, owner-scoped data
  with row level security and a protected `/api/v1` API, on **either** database provider. **It requires
  `zod=true`, `rest_api=true` and `database=postgres` or `supabase`**, enforced by the template's own validator
  and not duplicated in devkit: `auth=true` without a prerequisite is rejected before anything is created
  (`devkit new`, exit 2) or changed (`devkit upgrade`, exit 2), and no prerequisite is ever switched on for you.
  It is independent of `forms`. The registry refuses it up front for template releases before 0.6.0.
- **Better Auth is the authentication system for both providers**; Supabase Auth is not used (the local
  Supabase stack keeps its Auth service disabled). The decision and its reasons are in
  `docs/architecture.md`, and the roadmap no longer plans a separate `auth=supabase-auth`.
- `devkit upgrade PROJECT --set auth=true` enables authentication on an existing project that has the
  prerequisites, alone or in the same step that moves it from template 0.5.x to 0.6.x. **`auth` is sticky**:
  once a project has it, `upgrade --set auth=false` is refused (exit 2, nothing changed), because removing
  authentication would orphan accounts and data ownership and is not automated. Repeating `auth=true` is fine.
  The database provider stays locked as before.
- A sticky option now carries its own explanation (`Option.sticky_reason`), and the comparison with the
  recorded answer is made on normalised text, so it works for booleans as well as for text options (answers are
  recorded as `true`/`false` and arrive as typed values).
- New offline contract snapshot `tests/contracts/web-core/0.6.0.json`, captured from the published template
  tag `v0.6.0` (all six snapshots verify against their tags).
- New tests for `auth`: the registry, generation with each provider and with and without Forms, template-owned
  rejection of each missing prerequisite, release gating, the supported range, upgrades (selections kept, enabled
  later, invalid input fails safely), the sticky refusal, version reporting, and live-gate tests against the
  real template. The mini template used by the tests gained a v0.6.x line.
- Upgrading a Supabase project that has already started its local stack: the CLI creates `supabase/.temp` and
  `supabase/.branches`, which templates before 0.6.0 did not ignore, and `devkit upgrade` refuses a working tree
  with untracked files. Add those two paths to the project's `.gitignore` and commit it first; template 0.6.0
  ignores them for new projects. `docs/usage.md` says so.
- Version bumped to 0.7.0 (`uv.lock` changed by that one line only).

## 0.6.0

Adds the Web Core `database` option and widens the supported template range to `>=0.1.0,<0.6.0`
(template 0.1.x to 0.5.x). Requires nothing new to be installed; no dependency changed.

- New option `--set database=none|postgres|supabase` for `web-core` (default `none`; first available in
  template 0.5.0): a local PostgreSQL 17 database with SQL migrations and a typed, server-only data-access
  layer, run with Docker Compose (`postgres`) or the pinned Supabase CLI's local stack (`supabase`). It is a
  **choice**, not a boolean, so a project selects one provider. **It requires `zod=true`**, enforced by the
  template's own validator and not duplicated in devkit: `database=postgres` without `zod=true` is rejected
  before anything is created (`devkit new`, exit 2) or changed (`devkit upgrade`, exit 2). It is independent of
  `forms` and `rest_api`. The registry refuses it up front for template releases before 0.5.0, and devkit
  itself rejects any value other than `none`, `postgres` and `supabase` before a template is read.
- Registry: an `Option` can declare its closed set of `choices`, and can be `sticky`.
- `devkit upgrade PROJECT --set database=postgres` enables a database on an existing Zod project (alone, or in
  the same step that moves it from template 0.4.x to 0.5.x). **A sticky option cannot be changed by
  `upgrade` once it is set to something other than its default**: switching an established project between
  `postgres` and `supabase`, or back to `none`, is refused (exit 2, nothing changed). It swaps the tooling
  under existing data and moving data between providers is not automated; generate a new project with the
  other provider and move the data deliberately. Repeating the established provider is fine, and every other
  option can still be changed.
- New offline contract snapshot `tests/contracts/web-core/0.5.0.json`, captured from the published template
  tag `v0.5.0` (all five snapshots verify against their tags).
- New tests for `database`: the registry and its choices, generation with each provider and with and without
  Forms and the REST API, rejection before creation, release gating, the supported range, upgrades (selections
  kept, enabled later, invalid input fails safely) and the provider lock, version reporting, and live-gate
  tests against the real template. The mini template used by the tests gained a v0.5.x line.
- Version bumped to 0.6.0 (`uv.lock` changed by that one line only).

## 0.5.0

Adds the Web Core `rest_api` option and widens the supported template range to `>=0.1.0,<0.5.0`
(template 0.1.x to 0.4.x). Requires nothing new to be installed; no dependency changed.

- New option `--set rest_api=true|false` for `web-core` (default `false`; first available in template
  0.4.0): the versioned REST API v1 (route handlers under `/api/v1`, shared Zod contracts, RFC 9457
  problem-details errors, handler tests). **It requires `zod=true`.** As with `forms`, the rule is
  enforced by the template's own validator, not duplicated in devkit: `rest_api=true` without
  `zod=true` is rejected before anything is created (`devkit new`, exit 2) or changed
  (`devkit upgrade`, exit 2), and `rest_api` never turns Zod on. It is independent of `forms`. The
  registry refuses the option up front for template releases before 0.4.0 (exit 2).
- `devkit upgrade PROJECT --set rest_api=true` enables the API on an existing Zod project, alone or in
  the same step that moves it from template 0.3.x to 0.4.x. Selections (`zod`, `forms`,
  `cache_components`) and user work survive; the new option stays off unless asked for. The template
  adds files only, so dependencies and the lockfile do not change.
- New offline contract snapshot `tests/contracts/web-core/0.4.0.json`, captured from the published
  template tag `v0.4.0` (all four snapshots verify against their tags).
- New tests for `rest_api`: registry, generation with and without Forms, rejection before creation,
  release gating, the supported range, upgrades (selections kept, enabled later, invalid input fails
  safely), version reporting, and live-gate tests against the real template. The mini template used by
  the tests gained a v0.4.x line.
- Version bumped to 0.5.0 (`uv.lock` changed by that one line only).

## 0.4.0

Adds the Web Core `forms` option and widens the supported template range to `>=0.1.0,<0.4.0`
(template 0.1.x, 0.2.x and 0.3.x). Requires nothing new to be installed; no dependency changed.

- New option `--set forms=true|false` for `web-core` (default `false`; first available in template
  0.3.0): React Hook Form with the Zod resolver and a small accessible example form. **It requires
  `zod=true`.** That rule is enforced by the template's own validator, not duplicated in devkit:
  `forms=true` without `zod=true` is rejected before anything is created (`devkit new`, exit 2) or
  changed (`devkit upgrade`, exit 2), and `forms` never turns Zod on. The registry refuses the option
  up front for template releases before 0.3.0 (`--template-ref v0.2.x --set forms=true`, exit 2).
- `devkit upgrade PROJECT --set forms=true` enables Forms on an existing Zod project (alone, or in the
  same step that moves it from template 0.2.x to 0.3.x). Selections (`zod`, `cache_components`) and
  user work survive; a feature the new release introduces stays off unless asked for.
- New offline contract snapshot `tests/contracts/web-core/0.3.0.json`, captured from the published
  template tag `v0.3.0` (all three snapshots verify against their tags).
- New tests for Forms: registry, generation, rejection before creation, release gating, the supported
  range, and upgrades (selections kept, Forms enabled later, invalid input fails safely). The mini
  template used by the tests gained a v0.3.x line; the live gate (`pytest -m integration`) also generates
  Forms projects from the real template.
- Version bumped to 0.4.0 (`uv.lock` changed by that one line only).
- CI now uploads downloadable test evidence for every run and Python version, including failed runs:
  JUnit XML, the console record, run metadata tied to the commit under test, and installed package
  versions (`docs/ci-evidence.md`). The exit code is unchanged; a quiet token-shaped-string scan (matches
  are never printed) gates both the job summary and the upload.

## 0.3.0

- **`devkit upgrade PROJECT`** (`--dry-run`, `--to`, `--set`): upgrades an existing project to the newest
  template release this devkit supports. It requires a git root with nothing uncommitted, keeps recorded
  feature selections, refuses unsupported, older, unreleased or unpublished transitions, merges rather
  than overwrites, and exits 3 naming files when conflicts remain. It never commits or deletes.
- New profile option `zod` (`devkit new --set zod=true`), provided by template 0.2.0.
- **Backward compatible with template 0.1.x:** the supported range is `>=0.1.0,<0.3.0`. Options declare
  the release they first appear in (`since`); an option the selected release lacks is refused up front
  (Copier would silently ignore it), and after generation `devkit` verifies every requested option was
  recorded. Options also declare their default, checked against the template.
- **Offline contract snapshots** (`tests/contracts/web-core/<version>.json`, `tools/capture_contract.py`):
  CI now verifies compatibility with every supported release without credentials or network. The live
  comparison against the real template is the release gate (`pytest -m integration`).
- `devkit new` prints the selected options (`Options: zod=true`), also in dry runs.
- Booleans: `devkit` accepts only `true`/`false`; the template itself is now strict as well.
- **Safety:** `tools/scratch.py` (disposable workspaces with validated cleanup), a test that fails if code
  or documented snippets contain recursive deletes, `git clean`, `git reset --hard` or forced pushes, and
  a "Destructive commands" section in `AGENTS.md`.
- Validation: `--to` and option arguments are checked before the project is inspected.
- Documentation: feature-composition decision record, full-stack roadmap, release and upgrade strategy.
- Contract snapshots exist for template 0.1.0 and 0.2.0, both captured from their release tags
  (`tools/capture_contract.py`). Requires template v0.2.0 for the `zod` option; template v0.1.x remains supported.

## 0.2.0

- The Web Core template moved to its own repository, `web-core-template`, with its own versions.
- `devkit new` builds from a profile's published template at the newest supported release and
  records the portable repository URL. New options: `--template PATH_OR_URL` (local development or
  alternative origin), `--template-ref`, `--set NAME=VALUE`.
- Profiles declare the supported template range, Node major and options (`profiles.py`). Releases
  outside the range are refused.
- Answer validation moved into the template; the CLI keeps only path-safety and option checks.
- Removed the reserved-npm-name rule: npm accepts such project names.
- GitHub Actions CI on Linux for Python 3.12 and 3.14 (`uv run --locked pytest`) with commit-pinned
  actions and read-only permissions.
- Private-repository support: `doctor` reports whether a git credential helper is configured, and an
  unavailable template explains private-repository access. `devkit` never handles credentials.
- New error hierarchy with explicit exit codes; template unavailability is reported cleanly;
  credentials are redacted from messages.

## 0.1.0

- Initial release: `doctor`, `new`, `new --dry-run`, the Web Core template in the same repository.
