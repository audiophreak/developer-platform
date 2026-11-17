# Changelog

devkit versions are git tags (`vMAJOR.MINOR.PATCH`), independent of template versions.

## Unreleased

- CI now uploads downloadable test evidence for every run and Python version, including failed runs:
  JUnit XML, the console record, run metadata tied to the commit under test, and installed package
  versions (`docs/ci-evidence.md`). The exit code is unchanged; a quiet token-shaped-string scan (matches
  are never printed) gates both the job summary and the upload. No release is implied by this change.

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
