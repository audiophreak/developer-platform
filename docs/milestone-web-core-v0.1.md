> **Historical.** This report describes the single-repository v0.1 layout. The template has since moved to its own repository; see `milestone-v0.2-repository-split.md` and `architecture.md` for the current structure. The reserved-npm-name rule described below was later removed after testing showed npm accepts those names.

# Milestone: Web Core v0.1

Status: implemented and verified; **nothing is committed, tagged, pushed or published.**
The reference application was only read.

## What was delivered

| Requirement                                   | Delivered                                                                 |
| --------------------------------------------- | ------------------------------------------------------------------------- |
| Documented repository structure               | `README.md`, `docs/architecture.md`, `docs/usage.md`, this report         |
| Read-only prerequisite checks                 | `devkit doctor` (`src/devkit/doctor.py`) and `Brewfile`                   |
| Copier template derived from the baseline     | `copier.yml` + `template/`, personal and app-specific data removed        |
| Name, description, output directory, defaults | `devkit new NAME --description --output-dir`; description defaults to `A Next.js application` |
| Full Next.js baseline                         | Next 16, React 19, strict TS, Tailwind v4, shadcn/ui (Radix, Lucide), ESLint, Prettier, Vitest |
| Reusable AI instructions                      | `template/AGENTS.md`, `template/CLAUDE.md`; plus this repo's own          |
| Minimal CI workflow                           | `template/.github/workflows/ci.yml`: `npm ci`, `npm run check`            |
| Minimal CLI                                   | `doctor`, `new --dry-run`, local `new` for `web-core`                     |
| Smoke tests that generate and validate        | `tests/test_e2e.py` (real `npm ci` + `npm run check`) and `tests/test_generate.py` |
| Create and upgrade documentation              | `docs/usage.md`; the upgrade steps are exercised by `tests/test_upgrade.py` |

## Files created

All under `developer-platform` (new directory; `git init` run, no commits).

- Tooling: `pyproject.toml`, `uv.lock`, `.gitignore`, `Brewfile`, `AGENTS.md`, `CLAUDE.md`, `README.md`
- CLI: `src/devkit/{__init__,__main__,cli,doctor,generate,paths,profiles,validation}.py`
- Template: `copier.yml` and `template/` (25 files, listed by `find template -type f`)
- Tests: `tests/{conftest,test_validation,test_profiles,test_doctor,test_cli,test_generate,test_upgrade,test_e2e}.py`
- Docs: `docs/{architecture,usage,milestone-web-core-v0.1}.md`

Changes outside this directory: none to the reference app. Side effects on the workstation are
limited to a project-local `.venv`, the `uv` and `npm` download caches, and temporary directories
in the session scratchpad.

## Dependencies added

Python (exact pins, `exclude-newer = 2026-11-02`, `python-downloads = "never"`): `copier==9.19.1`
(runtime), `pytest==9.2.0` (dev), `hatchling==1.32.4` (build backend). Transitive versions are in
`uv.lock`. The generated project's npm dependencies are the reference app's, with five `^` ranges
pinned to the versions already locked (see `architecture.md`).

## Verification results

| Check                                                              | Result                  |
| ------------------------------------------------------------------ | ----------------------- |
| `uv run pytest` (everything)                                       | 93 passed, 24 s, exit 0 |
| `uv run pytest -m "not e2e"`                                       | 91 passed, 7 s          |
| `uv run pytest -m e2e` (`npm ci` + `npm run check` in 2 real apps) | 2 passed                |
| `uv run devkit doctor` on this workstation                         | exit 0 (1 warning: mise not installed, optional) |
| Manual: `devkit new demo-app --description <awkward>` then `npm ci`, `npm run check` | both exit 0 |
| Reference app after all work                                       | `git status` and `git diff --stat` identical to before; no files modified |

Failure behaviour covered by tests: invalid or reserved names, invalid descriptions, reserved
profiles (exit 2, nothing written); existing directory, empty directory, file and symlink at the
destination (refused, contents untouched); missing output directory; destination inside the
platform checkout; template rendering failure (reported, nothing left behind); `doctor` with an
empty `PATH` (exit 1); output never containing git identity values.

Tests were checked against deliberately planted defects (an unpinned Action, the reference app's
name leaked into the template, a type error in the generated app). Each was caught, and the files
were restored and compared byte-for-byte.

## Acceptance criteria

- Generator produces a working Web Core app: yes (end-to-end tests).
- Generated project passes `npm ci` and `npm run check`: yes, including with an awkward description.
- Correct metadata, imports and instructions: tests assert package name and description, lockfile
  sync, the `@/` alias (via the Button and page tests), CI steps and instruction files.
- No references to the original app or personal directories: tests scan every generated file for
  the reference app's name, `/Users/`, the home directory, the username and the git identity.
  **One deliberate exception:** `.copier-answers.yml` records the template location
  `developer-platform` (see below).
- Dry run and failure behaviour tested: yes.

## Findings and decisions made

1. **Location.** `developer-platform` did not exist; it was created as a sibling of the reference
   application.
2. **Copier needs a recorded template source.** Copier writes `_src_path` into every generated
   project and needs it (with `_commit`) to upgrade. Recording the absolute path would leak your
   home directory, so `devkit` records a home-relative path (`~/...`). It contains no user name
   but is still a local path. Publishing the repository removes it.
3. **Upgrades need a committed, tagged template.** The platform has no commits yet, so projects
   generated now record a throwaway commit id and cannot be upgraded cleanly. `devkit new` warns.
   Verified against a tagged copy: upgrades work and keep local edits.
4. **Copier silently ignores uncommitted edits once a tag exists** unless given an explicit ref;
   `devkit` always passes one.
5. **No global installs were needed.** Copier runs from a project-local `uv` environment; mise
   and Copier remain uninstalled on the workstation.
6. **`cn` and `lucide-react` pins** carried over from the reference; no new npm dependencies.
7. **Description is restricted** to a conservative ASCII set so Prettier and Markdown cannot
   reformat it and break `npm run check`.

## Unresolved issues

1. Publish the platform (decides the recorded template URL and gives a first tag). Needs your
   approval; nothing has been pushed.
2. Commit and tag the platform before generating projects you want to upgrade.
3. The reference application's shadcn work is still uncommitted; the template reflects its working
   tree. If you change it before committing, re-derive the template (procedure in `usage.md`).
4. `npm audit` findings carry over from the reference (dev-only `minimatch`, `ts-morph` and
   `deepmerge` advisories through the lint and shadcn tooling; production audit is 0). The
   template has no way to fix them until upstream releases do.
5. Full-stack and native iOS profiles, features, repository creation (`gh`), `devkit upgrade`
   and the platform's own CI are reserved for later milestones.
