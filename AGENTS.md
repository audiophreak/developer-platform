# Project rules

This repository is the developer platform: the Python CLI `devkit`, workstation tooling and the
profile registry. Templates live in their own repositories (`web-core-template`) with their own
versions. Generated applications carry their own `AGENTS.md` from their template.

## Commands

- `uv sync` — create the project-local environment from `uv.lock`
- `uv run devkit doctor` / `uv run devkit new NAME --dry-run`
- `uv run pytest` — all tests (no network; the contract test against `../web-core-template`
  skips if that checkout is absent)

## Working agreement

- Plan first for anything beyond a trivial fix; wait for approval on architectural decisions.
- Keep changes small and focused. Do not add, upgrade or remove dependencies without approval;
  pin exact versions (`pyproject.toml`, `uv.lock`) and keep the two-week release-age rule.
- Do not commit, push, tag, publish, deploy or rewrite history unless explicitly asked. Never move
  or delete a published tag.
- Never run anything that installs software globally or changes workstation configuration;
  `doctor` stays read-only.
- Never overwrite or delete user data. `devkit new` must keep refusing existing destinations.
- Work is not done until `uv run pytest` passes. Report actual results, including failures.
- Update `README.md`, `CHANGELOG.md` and `docs/` when behaviour changes.

## Boundary with templates

- The dependency is one-way: this repository declares which template releases it supports
  (`profiles.py`); templates must not know about devkit.
- Rules about an application's content (name, description, answers) belong in the template's
  `copier.yml`, never mirrored here. This repository checks only path safety and declared options.
- A template release that changes the contract (Node major, questions) needs a matching change to
  the registry's range, `node_major` or options, and the contract test must pass against it.
- Published mode must render a release tag inside the supported range, never a branch or an
  untagged commit. Local mode (`--template PATH`) is for development only.

## Secure coding

- Treat every CLI argument and answer as untrusted: validate before use, never build shell
  strings (use argument lists), never prompt for credentials, and never echo secrets or identity
  values in output or logs (redact URL credentials).
