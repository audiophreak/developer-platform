# developer-platform

A reusable, configurable AI-assisted development platform. It checks a macOS workstation and
generates new applications from independently versioned [Copier](https://copier-org.github.io/copier/)
templates through a small Python CLI, `devkit`.

It is one of three source repositories, each with its own version line:

| Repository                      | Contains                                                              |
| ------------------------------- | --------------------------------------------------------------------- |
| `developer-platform` (this one) | the `devkit` CLI, `Brewfile`, `doctor`, the profile registry (which template releases are supported, and which native and web releases pair), contract snapshots, platform docs |
| `web-core-template`             | the Web Core Copier template, its validation, tests and upgrade docs   |
| `native-ios-template`           | the native iOS add-on Copier template, applied to the same project directory as a second layer; owns only `ios/` and `.copier-answers.ios.yml` |

The dependency is one-way: this repository declares the template releases it supports (`src/devkit/profiles.py`); the
templates know nothing about it. At devkit 0.8.x: web `>=0.1.0,<0.8.0`, native `>=0.1.0,<0.2.0`, and native 0.1.x pairs
with web `>=0.7.0,<0.8.0`.

**v0.8:** `devkit doctor`, `devkit new` (with `--dry-run`, `--set`, `--template`,
`--template-ref`, `--native-*`), `devkit upgrade` (`--layer`), `devkit status`, `devkit native add` and three profiles:
`web-core`, `full-stack` (web + Zod + REST API + auth + a database you choose) and `native-ios` (full-stack plus a native
SwiftUI app, a generated typed API client and Keychain storage). See [docs/native-ios.md](docs/native-ios.md).
By default `devkit new` builds from the published (private) template at the newest release this
devkit supports, using git credentials you have configured, and records that repository's URL; `--template PATH` renders a local checkout for template
development. Web Core options: `cache_components`, `zod`, and `forms` (React Hook Form), `rest_api` (REST API v1) and `database`
(`none`, `postgres` or `supabase`), which require `zod`, and `auth` (Better Auth, which requires `zod`, `rest_api` and a `database`).

## Quick start

```bash
uv sync                                   # project-local environment from uv.lock
uv run devkit doctor                      # read-only prerequisite check
uv run devkit new my-app --output-dir .. --dry-run
uv run devkit new my-app --description "What it does" --output-dir ..
uv run devkit new scratch --template ../web-core-template --output-dir ..   # development
uv run devkit upgrade ../my-app --dry-run                 # preview an upgrade of an existing project
```

Examples assume the two repositories are sibling directories; `--output-dir ..` creates the new
app next to them.

```text
```

## Repository layout

```
.github/workflows/     CI: runs the test suite on pull requests and pushes to main
Brewfile              macOS prerequisites (checked by `doctor`, installed by you)
src/devkit/           cli, doctor, generate, upgrade, sources, profiles, validation, errors, gitutil, paths
tools/                scratch.py (safe cleanup), capture_contract.py (template contract snapshots)
tests/                unit and safety tests; fixtures/mini_template is a stand-in template; contracts/ holds
                      per-release snapshots of the template's questions
docs/                 architecture.md, usage.md, publishing.md, milestone reports
pyproject.toml        exact-pinned Python dependencies; uv.lock is the lockfile
AGENTS.md             rules for AI agents working on this repository (CLAUDE.md imports it)
CHANGELOG.md          release notes for devkit
```

## Documentation

- [Architecture](docs/architecture.md): the two-repository boundary, the template contract, Copier
  drawbacks, profiles and features, Next.js configuration review, security posture, corrections.
- [Usage](docs/usage.md): creating projects, local template development, upgrading, tests.
- [Publishing](docs/publishing.md): the exact steps to release both repositories.
- [CI test evidence](docs/ci-evidence.md): the JUnit XML, console record and metadata every CI run uploads,
  and how to retrieve and read them.
- [Next-session handoff](docs/NEXT_SESSION.md): current state, versions, branches, unresolved decisions and the
  release sequence.
- [Feature composition](docs/feature-composition.md): how optional features are represented, enforced,
  locked, recorded and upgraded (decision record), the [full-stack roadmap](docs/full-stack-plan.md)
  and the [release and upgrade strategy](docs/release-strategy.md).
- [Release-hardening report](docs/milestone-release-hardening.md) (incident analysis, strict booleans,
  compatibility, `devkit upgrade`, contract strategy) and the earlier
  [feature-composition report](docs/milestone-feature-composition.md).
- [Release preparation](docs/milestone-release-preparation.md), the
  [v0.2 milestone report](docs/milestone-v0.2-repository-split.md) and the
  [v0.1 report](docs/milestone-web-core-v0.1.md) (historical).
