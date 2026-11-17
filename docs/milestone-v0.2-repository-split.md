# Milestone: repository split (v0.2)

Status when written: implemented and verified locally, nothing yet committed or published. No
global tool or Claude setting was changed. The reference application was only read.

## What changed

The Web Core template moved out of this repository into `web-core-template`, a Copier
template with its own git history, version tags, tests and docs. This repository keeps the CLI,
workstation tooling, profile registry and platform docs, and is now version 0.2.0 (the template
starts at its own `v0.1.0`).

Added: published-mode generation from a tagged release with a portable recorded origin;
local development mode (`--template PATH`); `--template-ref`; `--set NAME=VALUE`; a profile
registry that declares the supported template range, Node major and options; an error hierarchy
with explicit exit codes; credential redaction; the template option `cache_components`.
Removed: the reserved-npm-name rule (unjustified), and validation mirrored between repositories.

## Requirement by requirement

| # | Requirement | Result |
| - | ----------- | ------ |
| 1 | Do not modify the reference application | Unchanged: same branch, 7 status entries, identical diff stat, no files modified. |
| 2 | Keep generator functionality and tests | All v0.1 behaviour kept. Coverage mapping below; total 187 passing tests (was 93). |
| 3 | Clear platform/template version boundary | Separate repositories and tags. The platform's `TemplateSpec` declares supported range, Node major and options; the dependency is one-way; a contract test checks the registry against the real `copier.yml`. |
| 4 | Portable origin in published mode | Verified: a project generated from an https-style origin records exactly that URL and the release tag (`_src_path`, `_commit`), with no local path. |
| 5 | Local development without publishing | `devkit new --template PATH` and Copier with `--vcs-ref HEAD`; the template repo's tests render from a snapshot, independent of commits and tags. |
| 6 | Generation from versioned git sources | Tested in both repos: tags, newest-supported selection, explicit tags, out-of-range, prerelease and non-release tags, annotated and lightweight tags, a bare repo as remote, and an https-style origin served by git `insteadOf`. |
| 7 | Upgrade older tag to newer tag, user-modified file preserved | `web-core-template/tests/test_upgrade.py` on the real template: user edit to `src/app/page.tsx` and a README note survive; template changes merge; a conflict leaves inline markers and loses nothing; a dirty project is refused unchanged. `devkit` projects upgrade via their recorded origin too (platform test). |
| 8 | Unavailable template, existing destination, failed generation | Tested at library and CLI level: unreachable or unpublished origin (exit 1), no supported release, missing tag, existing directory, empty directory, file and symlink (refused, untouched), template syntax error (reported, nothing left). |
| 9 | Review Next.js configuration | Done; see `architecture.md`. `cacheComponents` + `partialPrefetching` became one option, `cache_components` (default on). Other settings kept with reasons. |
| 10 | Re-run everything, including end-to-end | Results below. |

## Verification results

| Check | Result |
| ----- | ------ |
| `web-core-template`: `uv run pytest` | 66 passed, 44 s, includes `npm ci` + `npm run check` in three generated apps (defaults, awkward description, `cache_components` off) |
| `developer-platform`: `uv run pytest` | 121 passed, 1 skipped, 16 s |
| The skip | `test_published_releases_are_not_older_than_the_supported_range` needs a template release tag; passes once `v0.1.0` exists |
| `devkit doctor` | exit 0, one optional warning (mise not installed) |
| Manual CLI runs against the real template | dry run, real run with `--set cache_components=false`, invalid name (exit 2), default mode with nothing published (exit 1, clear message) |
| Flags-on `next.config.ts` vs reference app's | byte-identical |
| Mutation probes | Six planted defects (v0.1: unpinned Action, leaked app name, type error; v0.2: supported-range check removed, overwrite guard removed, option gating broken) were each caught; files restored byte-for-byte |
| Secret and machine-path scan of both repos | Only the test assertions that look for those strings |

### Where the v0.1 tests went

| v0.1 test file | Now |
| -------------- | --- |
| `test_generate.py` content tests (files, metadata, pins, lock sync, CI, instructions, no unrendered syntax, no personal references, awkward descriptions) | `web-core-template/tests/test_render.py` |
| `test_validation.py` (name and description rules, copier.yml parity) | `web-core-template/tests/test_render.py` (Copier enforces the rules in `copier.yml` itself; no mirror remains) |
| `test_e2e.py` | `web-core-template/tests/test_e2e.py` (plus a `cache_components=false` app) |
| `test_upgrade.py` | `web-core-template/tests/test_upgrade.py` (real template, remote, conflicts, dirty tree) |
| `test_generate.py` safety tests (dry run, existing paths, missing output dir, inside checkout, failure rollback) | `developer-platform/tests/test_generate.py`, now also for published and local modes |
| `test_cli.py`, `test_doctor.py`, `test_profiles.py` | same files, extended |

## Findings and changed assumptions

1. **`main` of the reference application did not contain the shadcn/ui baseline** when the split
   was built; the template was derived from an uncommitted working tree. Resolved before release
   preparation: the baseline is merged (PR #2, commit `f244594`) and the template was then compared
   against it (`web-core-template/docs/provenance.md`).
2. **The reserved-npm-name rule was wrong** and is removed (tested against npm 11).
3. **Plain `copier update` ignores the supported range** and takes the newest tag. Upgrade docs
   pin `--vcs-ref`; a test records the hazard. A `devkit upgrade` command would close it and is a
   candidate for the next milestone.
4. **Copier's `Worker` is internal-only**, so option validation is declared in the profile registry
   and checked against the real `copier.yml` by the contract test instead of introspecting Copier.
5. **Copier validation errors are recognised by their message prefix.** The version is pinned and a
   test fails if the wording changes.
6. **A bare repository path is an origin, not a checkout**; the first version of source
   resolution misclassified it and a test caught it.
7. **The registry's template URL is an assumption** (`github.com/audiophreak/web-core-template`).

## Unresolved issues

1. Publication and the owner/visibility choices (`publishing.md`). Until a release tag exists,
   `devkit new` without `--template` fails with "Template source is unavailable".
2. How `full-stack` and `native-ios` compose across templates (layering vs one template); needs a
   prototype before that milestone.
3. No CI workflow or branch protection for either repository, by design.
4. `npm audit` findings carry over from the reference (dev-only tooling advisories; production
   audit is 0).
5. The `uv` and `npm` download caches, Copier's git cache (`~/Library/Caches/copier`) and the
   session scratchpad were written to; no other workstation state changed.
