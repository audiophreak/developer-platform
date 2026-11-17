# Milestone: release hardening for template 0.2.0 and devkit 0.3.0

Status: implemented and verified locally on the feature branches. **Nothing is committed, tagged,
pushed or published.** The reference application was only read; released tags `v0.1.0` and `v0.2.0`
and the history of `main` in both repositories are untouched.

## 1. The destructive-command incident

**What happened.** In the previous milestone one command contained `rm -rf /dev/null 2>/dev/null`,
placed between an `echo` and the assignment of the scratch directory it was meant to prepare.

**Why it was constructed.** There was no purposeful reason. The only reading the command supports is
that I meant to clear a scratch directory before regenerating into it, and wrote a literal system path
in the position where a variable (not yet assigned on that line) belonged. The directory did not exist,
so nothing needed clearing; the delete was both unnecessary and wrong. It broke a pattern I had
already adopted earlier in the session after the harness blocked a relative-glob delete: use a fresh
unique directory instead of clearing one.

**What executed, and its exit status.** The command ran as uid 501 and was not blocked by the harness.
Its own exit status was **not observed**: its error output was discarded by the `2>/dev/null`, and the
status shown was that of the later `uv` command in the same line. That discarded error output is itself
a defect in the command. The most likely status is non-zero (permission denied), which the evidence
below supports but which cannot be proven without re-running it; the command was deliberately not
re-run.

**Whether any filesystem object was affected: no.** Evidence gathered afterwards, read-only:

- `/dev` is `dr-xr-xr-x root wheel` on a `devfs` mount and is not writable by uid 501, so an unlink
  of any entry cannot succeed for this user.
- `/dev/null` is still a character device (3,2), inode 336, between `/dev/tty` (335) and `/dev/zero`
  (337); a write to it succeeds and a read returns end of file.

**What should have prevented it, and what now does.**

| Layer | Before | Now |
| ----- | ------ | --- |
| My own discipline | A pattern, not a rule | Written rules in both repositories' `AGENTS.md` ("Destructive commands"): never hand-written recursive or forced removal, `find -delete`, `git clean`, `git reset --hard`, forced pushes or recursive chmod; prefer fresh unique directories; never hide a state-changing command's errors; anything removing user data needs approval |
| Tooling | None | `tools/scratch.py`: `new` creates a marked workspace under the system temp directory; `clean` deletes only paths provably inside a workspace it created (refuses symlinks, `..` escapes, `/`, the home directory, the current directory, unmarked directories, special files); every child is validated before any is removed |
| Validation in the repository | None | A test fails if code, CI or documented shell snippets contain recursive deletes, `find -delete`, `git clean`, `git reset --hard`, forced pushes or recursive chmod/chown; it has a negative control using the exact incident command, and it works without git |
| Tests of destructive behaviour | n/a | System paths (`/dev/null`, `/`, the home directory) are given only to the pure validator `assert_removable`; nothing that can delete is pointed outside a pytest temporary directory |

The harness had no objection to this command (it had blocked a different one earlier), so it cannot be
relied on as the only safeguard. I could not mechanically re-audit every earlier shell command in the
session; the scratch-directory cleanups I recall used a variable set on the same line. Global Claude
settings were not changed.

## 2. Feature input validation

Copier casts a `type: bool` answer before validators run, so no validator can reject `banana`.
Candidates were tested side by side with the same inputs through the Python API and the real command
line (`feature-composition.md` has the table). **Adopted:** `type: yaml` with `choices: [false, true]`
and an `is boolean` validator, for every boolean question including the existing `cache_components`.

- `banana`, `1`, `0`, `2`, `y`, `n`, `tRuE`, an empty value and null are rejected before anything is
  written; `true`/`false`, `yes`/`no`, `on`/`off` in lower, Title or UPPER case are accepted and
  recorded as real booleans.
- One copy of the rule, in `copier.yml`; identical through `devkit` and direct Copier; interactive
  users get a select list. `devkit --set` additionally accepts only `true`/`false`.
- Projects generated with the old `type: bool` questions keep working: tested by upgrading a project
  generated with the lenient form to the strict one, with answers preserved.
- 93 regression tests (`tests/test_answer_types.py`): the strict form for every boolean question,
  valid and invalid values through the API and the command line, defaults, and the legacy upgrade.

## 3. Template backward compatibility

devkit 0.3.0 **keeps support for template 0.1.x**: range `>=0.1.0,<0.3.0`. The contract is `app_name`,
`app_description`, the declared options and the Node major; all exist in both lines, and `zod` is the
only difference. Options now declare `since`: `--set zod=true` against 0.1.x is refused up front
(Copier would silently ignore it), a pinned 0.1.x generates normally with the options it has, a local
checkout is judged by its own `copier.yml` at the ref being rendered, and after generation `devkit`
verifies each requested option was recorded. Version-specific contract tests: snapshots of v0.1.0 (from
the real tag) and 0.2.0, plus a real generation from the actual v0.1.0 tag in the live gate.

## 4. `devkit upgrade`: implemented

`devkit upgrade PROJECT [--to vX.Y.Z] [--set N=V] [--profile] [--dry-run]`, one module and one
subcommand. It identifies the source and installed release from `.copier-answers.yml`; enforces the
supported range; refuses a dirty or non-root repository, an installed release that is unreleased,
unsupported or too old/new, downgrades and unpublished or out-of-range targets; keeps recorded
selections (new features stay off unless `--set`); refuses options the target lacks; previews with
`--dry-run` (verified to change nothing); merges without overwriting; reports conflicts with exit 3
while keeping both sides; never commits or deletes. 32 tests, and a rehearsal on the real template.

## 5. Cross-repository contract tests in CI

Decision: **offline snapshots for CI, the live comparison as a release gate; no credentials.**
`tests/contracts/web-core/<version>.json` snapshots (captured from release tags by
`tools/capture_contract.py`) are checked against the registry offline, so CI covers every supported
release. `pytest -m integration` proves each snapshot still equals the real template. The five earlier
skips are gone as a compatibility gap; in a CI-like run 9 live tests still skip, which is the release
gate and not the protection. Alternatives (a read token, cross-repository checkout) and why not:
`release-strategy.md`, section 6.

## 6. Files changed (all uncommitted)

**`developer-platform`**: modified `AGENTS.md`, `CHANGELOG.md`, `README.md`, `docs/architecture.md`,
`docs/usage.md`, `pyproject.toml` (pytest `pythonpath` only; no dependency change; `uv.lock` unchanged),
`src/devkit/{cli,errors,generate,profiles,sources,validation}.py`, `tests/conftest.py`, the mini
fixture template, and `tests/test_{cli,generate,integration_web_core,profiles,sources,validation}.py`.
Added `src/devkit/upgrade.py`, `tools/scratch.py`, `tools/capture_contract.py`, `tests/contracts/`
(two snapshots), `tests/test_{compatibility,contract_snapshots,no_destructive_commands,scratch,upgrade}.py`,
and `docs/{feature-composition,full-stack-plan,release-strategy,milestone-feature-composition,milestone-release-hardening}.md`.

**`web-core-template`**: modified `AGENTS.md`, `CHANGELOG.md`, `README.md`, `copier.yml` (strict
booleans), `docs/maintaining.md`, `docs/upgrading.md`, `template/package.json.jinja`,
`template/README.md.jinja`, `template/AGENTS.md.jinja` (renamed), `pyproject.toml`,
`tests/{conftest,test_e2e,test_render,test_upgrade}.py`. Added `features.yml`, `locks/` (base moved,
`zod.json`), `docs/features.md`, the conditional `schemas` directory, `tools/{features,refresh_locks,compare_release}.py`,
and `tests/test_{answer_types,compare_release,features,lock_matrix,no_destructive_commands,zod_feature}.py`.

## 7. Test results (exit codes 0 unless stated)

| Check | Result |
| ----- | ------ |
| Template `uv run --locked pytest` (incl. 5 end-to-end configurations) | **226 passed** |
| Platform `uv run --locked pytest` | **236 passed, 1 skipped** |
| The skip | The test that requires a template release to exist; it skips while the template has unreleased work |
| Platform live release gate `pytest -m integration` | 8 passed, 1 skipped (same test) |
| CI-like run (clean copy, no `.git`, no template beside it) | **228 passed, 9 skipped** (all live-gate tests), exit 0 |
| `refresh_locks.py --check` / `compare_release.py v0.1.0` / `devkit doctor` | exit 0 / exit 0 / exit 0 |

Four planted defects aimed at this milestone (upgrade without the clean-tree check, a wrong `since` in
the registry, the since-gate disabled, a lenient `type: bool` question) were each caught, and the files
restored byte-for-byte. The lint test was shown to catch the incident command planted in documentation.
Two failures found along the way were fixed: the lint test needed a fallback when git is absent, and
planning ignored a requested option when nothing newer was available.

## 8. Rehearsal with the real template (nothing published)

A scratch repository held the **real v0.1.0 tree** (`git archive`, tree hash identical to the real tag)
and the current working tree as v0.2.0, served at the registry URL through git's URL rewriting; a later
v0.2.1 changed the Zod schema file. The unmodified CLI ran against it.

| Step | Result |
| ---- | ------ |
| `devkit new` default (Zod off) and `--set zod=true` | resolved v0.2.0; answers record the GitHub URL, tag and booleans |
| Both configurations: lock vs `package.json`, exact pins, `npm ci`, `npm run check`, `npm audit --omit=dev` | consistent; exit 0 / 0 / 0; 3 and 21 tests; 0 vulnerabilities |
| Pinned real v0.1.0 (`--template-ref v0.1.0`) | generates, `npm ci` and `npm run check` exit 0; `--set zod=true` refused (exit 2, nothing created) |
| Upgrade the v0.1.0 project with user edits: `--dry-run`, then real | dry run changed nothing; real changed only `.copier-answers.yml`; `cache_components=false` and edits kept |
| Gate after that upgrade, then `upgrade --set zod=true` at the same release | `npm ci` and `npm run check` exit 0 (21 tests); lock matches; edits kept |
| Zod project with its own schema file upgraded v0.2.0 to v0.2.1 | selection kept, own file intact, template change merged, `npm ci` and `npm run check` exit 0 |
| Plain project upgraded to v0.2.1 | still no Zod, no schemas directory, gate passes |
| Scans of all generated apps | no credentials, emails, personal paths or references to other applications |

## 9. Release blockers and readiness

**No blockers found.** Before publishing: capture the 0.2.0 snapshot from the `v0.2.0` tag instead of
the working tree (`release-strategy.md`, section 7), bump the platform version to 0.3.0, and update both
changelog headings. Both repositories are otherwise ready for template `v0.2.0` and devkit `v0.3.0`.

Open decisions for you:

1. **A dependency.** Reading template question names from `copier.yml` could use `pyyaml` (already
   installed through Copier). I tried to declare it, the harness stopped that edit, and I used a small
   tested reader instead. Declaring it is a one-line change if you approve.
2. `devkit upgrade` goes to one target release; chaining several is deferred.
3. A feature cannot be switched off by `upgrade`; it is manual (documented).
4. The recorded Copier `_commit` for projects generated from an uncommitted template is a throwaway id;
   `upgrade` refuses such projects.
