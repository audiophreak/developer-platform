# Release preparation (developer-platform v0.2.0, web-core-template v0.1.0)

Status when written: both repositories were ready to publish and nothing had been committed,
tagged or pushed. Publication then followed `publishing.md`; the git tags and GitHub Actions runs
are the record of what was released. The reference application was only read.

## What was checked

| # | Check | Result |
| - | ----- | ------ |
| 1 | Reference baseline merged, working tree clean | PR #2 merged; `f244594` is on `main` and `origin/main` (`bf3643c`); 0 uncommitted changes. |
| 2 | Template compared with the merged reference | 16 of 22 shared files byte-identical; every difference intentional (see `web-core-template/docs/provenance.md`): exact pins, name and description, app-info module, README, CI workflow, answers file, no `public/*.svg`. All 719 lockfile entries identical. **No unexpected differences.** |
| 3 | CI for both repositories | Added; minimal, `contents: read`, commit-pinned actions, no credential persistence, no secrets, exact `uv` version. Properties enforced by `tests/test_ci_workflow.py` in each repository. |
| 4 | CI commands in a clean copy with the pinned `uv` (0.13.6) | `uv sync --locked` and `uv run --locked pytest` exit 0 for both (platform 123 passed, 5 skipped; template 73 passed). |
| 5 | Generator and versioned upgrade, end to end | Rehearsed with the real CLI against a scratch remote serving the registry URL: default mode resolved `v0.1.0`, recorded the real GitHub URL and tag; `npm ci` and `npm run check` exit 0; an upgrade to `v0.1.1` with `copier update --vcs-ref` preserved a user edit and a README note, merged the template change, left no conflict markers, and `npm run check` still exited 0. |
| 6 | All tests | Template: 73 passed, exit 0. Platform: 127 passed, 1 skipped, exit 0 (the skip needs a release tag). `devkit doctor`: exit 0. |
| 7 | Audits | See below. No new findings. |
| 8 | Release documentation | Reviewed against the tools: `gh` is logged in as the assumed owner with `repo` and `workflow` scopes, both repository names are free, the flags exist, `gh run watch` needs an explicit run id (fixed). Order is now template first, and tag only after CI is green. |
| 9 | Credentials, personal paths, machine assumptions | No credentials or emails. Personal `~/Developer/...` examples replaced with layout-neutral ones; personal details removed from the historical reports. Remaining mentions are the guard assertions in tests and the public owner handle in the registry URL and the publishing steps. |

## Audits

- **Generated app, `npm audit --omit=dev`:** 0 vulnerabilities, exit 0.
- **Generated app, `npm audit` (everything):** 10 moderate, exit 1. One advisory,
  GHSA-g3hv-75wg-m249 (`minimatch`), reached through the lint (`@typescript-eslint`) and shadcn CLI
  (`ts-morph`) tooling; every vulnerable package is dev-only in the lockfile. This is the known
  advisory from the reference application. It is down from 12 at the previous audit: the two low
  findings (`deepmerge`, `@shadcn/registry`) are no longer reported. **No new advisories.**
- **Python, both repositories:** `uv audit` reports no known vulnerabilities and no adverse project
  statuses in 24 packages each; a cross-check of every locked version against PyPI's records finds
  none.

## Findings during preparation

1. **A test that would have failed on other machines.** The "no developer identity in generated
   files" test matched the username as a word, which collides with legitimate template text for
   usernames such as `build`, `test`, `node`, `root` or `ubuntu`. It now treats an identity value as
   a leak only if it appears in the output but not in the template source; verified with seven
   usernames and with a planted leak.
2. **Python floor and Linux.** Local runs used Python 3.14 on macOS only. Both repositories' CI now
   runs a Python 3.12 and 3.14 matrix on Linux, which is the real test of the declared floor; tags
   are created only after a green run.
3. **Private repositories.** Both repositories are private (see `publishing.md`, "Private
   repositories"). `devkit` never handles credentials; `doctor` reports whether a git credential
   helper is configured.
4. **Platform CI skips the contract tests** (they need the template checked out, which needs a read
   token for the private template). A follow-up job could run them.

## Release blockers

None known. Decisions made: owner `audiophreak`, names as in the registry, and **both repositories
private**. See `publishing.md` for the sequence.
