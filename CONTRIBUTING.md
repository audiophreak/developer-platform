# Contributing

Thanks for your interest in the developer platform. It is a small, independently maintained project,
so focused changes with tests are the easiest to review.

## Development setup

Requirements: macOS or Linux, Git, [uv](https://docs.astral.sh/uv/) and Python 3.12 or later.

```bash
git clone https://github.com/audiophreak/developer-platform.git
cd developer-platform
uv sync --locked
uv run --locked pytest       # no network and no credentials needed
uv run devkit doctor         # read-only prerequisite check
```

The live release gate (`uv run pytest -m integration`) needs checkouts of `web-core-template` and
`native-ios-template` beside this repository; it is skipped otherwise.

## Ground rules

The full rules are in [AGENTS.md](AGENTS.md); they apply to people and coding agents alike. In short:

- Open an issue first for anything beyond a small fix.
- Do not add, upgrade or remove dependencies without discussion; pins are exact and at least two
  weeks old.
- Never add recursive or forced deletes, hidden errors or code that handles credentials.
- `uv run pytest` must pass. Update `README.md`, `CHANGELOG.md` and `docs/` when behaviour changes.
- Never commit credentials, personal data or machine-specific paths.

## Pull requests

CI runs the full test suite on Linux with Python 3.12 and 3.14 for every pull request. Releases are
git tags created by the maintainer after CI passes on `main` (`docs/release-strategy.md`).

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE).
Report security issues privately as described in [SECURITY.md](SECURITY.md).
