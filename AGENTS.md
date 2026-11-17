# Project rules

This repository is the developer platform: the Python CLI `devkit`, workstation tooling and the
profile registry. Templates live in their own repositories (`web-core-template`) with their own
versions. Generated applications carry their own `AGENTS.md` from their template.

## Commands

- `uv sync` — create the project-local environment from `uv.lock`
- `uv run devkit doctor` / `uv run devkit new NAME --dry-run`
- `uv run pytest` — all tests (no network, no credentials; the live checks against
  `../web-core-template` skip if that checkout is absent, the offline contract snapshots always run)
- `uv run python tools/capture_contract.py ...` — capture or verify a template contract snapshot
- `uv run python tools/scratch.py new|clean` — disposable workspaces with validated cleanup

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
  the registry's range, `node_major` or options (with their `since`), a new contract snapshot
  (`tools/capture_contract.py`, from the release tag), and the live release gate
  (`pytest -m integration`) must pass against it.
- Published mode must render a release tag inside the supported range, never a branch or an
  untagged commit. Local mode (`--template PATH`) is for development only.

## Destructive commands

An unscoped delete is only as safe as the path typed into it, so these are rules, not preferences:

- **Never** run recursive or forced removal by hand (`rm -r`, `rm -rf`), `find ... -delete`,
  `git clean`, `git reset --hard`, forced pushes or recursive `chmod`/`chown`. A test fails if any
  appear in the repository's code, CI or documented shell snippets.
- **Prefer not deleting.** Make a fresh, unique directory for every run (`uv run python
  tools/scratch.py new`, or `mktemp -d`) instead of clearing and reusing one.
- **When something must be removed, use `uv run python tools/scratch.py clean WORKSPACE [CHILD...]`.**
  It deletes only paths that are provably inside a workspace it created under the system temporary
  directory, and refuses symlinks, `..` escapes, `/`, the home directory and the current
  directory. Never write a literal system path, or a variable that might be empty, after a
  delete command.
- **Never hide a state-changing command's errors** (`2>/dev/null`); a failed delete must be visible.
- **Tests of destructive behaviour use pure validators.** Never point anything that can delete at a
  system path, not even one expected to be refused; test refusals with `assert_removable`.
- Anything that would remove user data, a repository, a tag or a branch needs the user's explicit
  approval first.

## Secure coding

- Treat every CLI argument and answer as untrusted: validate before use, never build shell
  strings (use argument lists), never prompt for credentials, and never echo secrets or identity
  values in output or logs (redact URL credentials).
