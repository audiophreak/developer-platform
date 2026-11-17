> **Partly superseded.** The follow-up milestone (`milestone-release-hardening.md`) resolved items 1 and 8 below (booleans are now strict in the template itself; devkit 0.3.0 keeps supporting template 0.1.x), implemented `devkit upgrade`, and replaced the CI contract-test gap with offline snapshots. Read it for the current state.

# Milestone: feature composition and optional Zod validation

Status: implemented and verified locally on feature branches (`feat/feature-composition` here,
`feat/optional-zod-validation` in `web-core-template`). **Nothing is committed, tagged, pushed or
published.** The reference application was only read. Released tags `v0.1.0` and `v0.2.0` are
untouched.

## What was built

- **Feature model** (decision record: `feature-composition.md`): a feature is a boolean Copier
  question plus a `features.yml` entry plus conditionally named files plus tests that ship in the
  generated project. Selection is recorded in `.copier-answers.yml` and survives upgrades.
- **Zod feature**: `devkit new --set zod=true` (or `copier --data zod=true`). Adds the exact-pinned
  `zod` 4.6.7, a shared schema module in `src/lib/schemas/` (`appInfoSchema`) and 18 tests showing
  accepted and rejected input, plus README and `AGENTS.md` guidance.
- **Lockfile matrix**: one committed lockfile per distinct npm dependency set (`locks/base.json`,
  `locks/zod.json`), selected at generation by a computed key through a one-line include. A
  maintainer tool generates feature locks from the base lock; tests verify them.
- **Release guard**: `tools/compare_release.py` proves the default configuration renders
  byte-identically to a previous release.
- **Plans**: `full-stack-plan.md` (roadmap for forms, API, database, auth, migrations, Docker, iOS)
  and `release-strategy.md` (versions, upgrades, `devkit upgrade`, CI contract tests).

## Files changed (all uncommitted)

**`web-core-template`**: modified `copier.yml`, `pyproject.toml` (pytest `pythonpath`),
`template/package.json.jinja`, `template/README.md.jinja`, `template/AGENTS.md` (now
`AGENTS.md.jinja`, a `git mv` rename that is staged), `template/package-lock.json.jinja`
(moved to `locks/base.json`, also a staged rename, and replaced by an include shim),
`README.md`, `AGENTS.md`, `CHANGELOG.md`, `docs/maintaining.md`, `docs/upgrading.md`,
`tests/conftest.py`, `tests/test_render.py`, `tests/test_upgrade.py`, `tests/test_e2e.py`.
Added `features.yml`, `locks/zod.json`, `docs/features.md`, the conditionally named directory
`template/src/lib/{% if zod %}schemas{% endif %}/` (3 files), `tools/features.py`,
`tools/refresh_locks.py`, `tools/compare_release.py`, and `tests/test_features.py`,
`test_lock_matrix.py`, `test_zod_feature.py`, `test_compare_release.py`.

**`developer-platform`**: modified `src/devkit/profiles.py` (zod option, option defaults, range
`>=0.2.0,<0.3.0`), `src/devkit/cli.py` (prints selected options), `README.md`, `CHANGELOG.md`,
`docs/architecture.md`, `docs/usage.md`, the mini fixture template (zod question and flags), and
`tests/test_cli.py`, `test_generate.py`, `test_integration_web_core.py`, `test_profiles.py`,
`test_sources.py`, `test_validation.py`. Added `docs/feature-composition.md`,
`docs/full-stack-plan.md`, `docs/release-strategy.md` and this report.

## Dependency and lockfile strategy

Exact pin in `package.json.jinja` (`zod` 4.6.7: newest stable release, published 35 days before
selection, MIT, no dependencies, no install scripts). Zod was already in the base lock as a
development-only transitive dependency of the shadcn CLI at the same version, so the Zod lockfile
differs from the base by two lines: it adds `zod` to the project's own dependencies and removes
the entry's `dev` flag. No package was added, removed or changed. Nothing is resolved at generation
and no Copier hook or `npm install` runs. See `feature-composition.md`, section 4.

## Test results (exit codes 0 unless stated)

| Suite | Result |
| ----- | ------ |
| `web-core-template`: `uv run --locked pytest` | **129 passed** (was 73), 71 s, including 5 end-to-end configurations |
| `developer-platform`: `uv run --locked pytest` | **142 passed, 1 skipped** (was 130), 17 s |
| The skip | The contract test that requires a template release to exist: it skips while the template checkout has unreleased work |
| `refresh_locks.py --check` | exit 0 ("up to date"): npm reproduces the committed Zod lockfile |
| `compare_release.py v0.1.0` | exit 0: default configuration identical to the released template |
| `devkit doctor` | exit 0 |

New template tests cover: the registry and the matrix logic with synthetic registries (requires,
conflicts, chains, cycles, unknown references, lock-key grouping, malformed registries); the lock
matrix (a lock for every key, no orphans, selected lock equals the registry's, additive over base,
registry sources and integrity hashes, no new install scripts, a size cap); the Zod feature (off:
no dependency, files, guidance or empty directories; on: exact pin, nothing else added, promoted
lock entry, module, tests, documentation, recorded answer, composition with `cache_components`);
answer types (including Copier's boolean coercion); controlled upgrades (selection survives, the
user's own schema file survives, template changes merge, a plain project stays plain, a feature
switched on later gets files, dependency and matching lockfile). New platform tests cover `--set zod`
alone and combined, strict boolean parsing (`maybe`, `banana`, `2`, empty), duplicates, unknown
options, dry-run with a feature, and the contract (every registry default equals the template's;
the real template generates with and without the feature).

## Generated-application verification

Both configurations were generated through the normal `devkit new` command and run through
`npm ci` and `npm run check`:

| App | Configuration | `npm ci` | `npm run check` | Tests |
| --- | ------------- | -------- | --------------- | ----- |
| plain-demo | default | exit 0 | exit 0 | 3 passed |
| zod-demo | `--set zod=true` | exit 0 | exit 0 | 21 passed (3 + 18 schema tests) |

The end-to-end suite additionally ran the same gate for the other three combinations (awkward
description, `cache_components` off, and Zod with `cache_components` off). Further evidence: strict
TypeScript fails on a deliberate type error in the schema module; the default app has no
`src/lib/schemas` directory and no empty directories; `package.json` and the lockfile agree in both
apps; `npm audit --omit=dev` exits 0 for both, and the full audit shows the one known dev-only
advisory (GHSA-g3hv-75wg-m249) in both, with no findings for Zod; scans of both apps found no
credentials, emails, personal paths or references to other applications.

## Template-upgrade implications

- A project keeps its selections; features introduced later default off. Upgrading a `v0.1.0`
  project to `v0.2.0` leaves it without Zod and with an unchanged lockfile.
- Switching Zod on later works with `copier update --vcs-ref <tag> --data zod=true`; switching off is
  manual.
- A dependency-set change replaces the lockfile by a three-way merge; it was clean in the tested
  case; fallback is resolving `package.json` and running `npm install`.
- Plain `copier update` still ignores the supported range: pin `--vcs-ref`; `devkit upgrade` is
  recommended next (`release-strategy.md`).

## Unresolved decisions and risks

1. **Raw Copier treats `--data zod=banana` as true**, and no validator can reject it (found while
   testing, pinned by a test). `devkit` is strict; direct users must write `true` or `false`.
2. **No real rule between features exists yet** (`zod` has no prerequisite), so the validator
   parity check is structural and the requires/conflicts logic is proven only on synthetic
   registries. `forms` will be the first real rule.
3. **The lockfile matrix** is capped at 16 by a test; beyond it, switch to curated presets.
4. **Layering add-on templates is a hypothesis**, needed before native iOS, and not prototyped.
5. **`copier update` conflicts** concentrate in `package.json` and the lockfile.
6. **Platform CI still skips the contract tests** (see `release-strategy.md`, question 6).
7. **Registry and template duplicate the option list**, guarded only by the contract test.
8. **This milestone's platform range drops template 0.1.x** (`>=0.2.0,<0.3.0`); devkit 0.2.0 remains
   the tool for 0.1.x.

## Recommended next increment

1. Release the template as `v0.2.0` and the platform as `v0.3.0` (`release-strategy.md`, section 7).
2. Then `devkit upgrade` and the CI contract job (devkit 0.4.0), before any breaking template
   release.
3. Then `forms` (template 0.3.0), the first feature with a prerequisite and with development
   dependencies.

## Process notes

- `git mv` staged two renames in `web-core-template`; they are index changes only, not commits.
- One command in this session contained a stray, pointless `rm -rf /dev/null`; it could not succeed
  without privileges (uid 501) and `/dev/null` was verified intact.
