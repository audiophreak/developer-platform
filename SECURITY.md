# Security policy

## Supported versions

Security fixes are made for the latest `devkit` release (the newest `vMAJOR.MINOR.PATCH` tag) only.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub: **Security › Report a vulnerability**
(https://github.com/audiophreak/developer-platform/security/advisories/new). Do not open a public issue
for a suspected vulnerability.

Include the `devkit` version (`uv run devkit --version`), your operating system, the command you ran and
the smallest reproduction you can. Do not include tokens, credentials, `.env` files or other secrets.
This is an independently maintained project: expect an acknowledgement within about a week. Fixes are
released as soon as practical, with credit if you would like it.

## Security posture

- `devkit` never reads, stores, logs or passes credentials. Git runs with prompting disabled
  (`GIT_TERMINAL_PROMPT=0`) and uses whatever credential helper you have configured; URL credentials
  are redacted from every message.
- Every CLI argument and answer is treated as untrusted: it is validated before use and never
  interpolated into a shell command (argument lists only).
- `devkit doctor` is read-only. Nothing in this repository installs software globally or changes
  workstation configuration.
- Published mode renders only release tags inside the supported range, never a branch or an untagged
  commit.
- Dependencies are exact-pinned in `pyproject.toml` and `uv.lock`, with a two-week release-age buffer
  (`exclude-newer`).
- CI uses read-only `GITHUB_TOKEN` permissions, `persist-credentials: false`, actions pinned to full
  commit SHAs, stores no secrets and does not run on `pull_request_target`.
