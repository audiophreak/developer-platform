# Changelog

devkit versions are git tags (`vMAJOR.MINOR.PATCH`), independent of template versions.

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
