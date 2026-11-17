# developer-platform

A reusable, configurable AI-assisted development platform. It checks a macOS workstation and
generates new applications from independently versioned [Copier](https://copier-org.github.io/copier/)
templates through a small Python CLI, `devkit`.

It is one of two repositories with separate version lines:

| Repository                      | Contains                                                              |
| ------------------------------- | --------------------------------------------------------------------- |
| `developer-platform` (this one) | the `devkit` CLI, `Brewfile`, `doctor`, profile registry, platform docs |
| `web-core-template`             | the Web Core Copier template, its validation, tests and upgrade docs   |

**v0.5:** `devkit doctor`, `devkit new` (with `--dry-run`, `--set`, `--template`,
`--template-ref`), `devkit upgrade` and one profile, `web-core`. Full-stack and native iOS profiles are reserved.
By default `devkit new` builds from the published (private) template at the newest release this
devkit supports, using git credentials you have configured, and records that repository's URL; `--template PATH` renders a local checkout for template
development. Web Core options: `cache_components`, `zod`, and `forms` (React Hook Form) and `rest_api` (REST API v1),
which require `zod`.

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
