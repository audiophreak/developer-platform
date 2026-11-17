# Using developer-platform

All commands run from the `developer-platform` checkout unless stated otherwise. Python
dependencies are installed into a project-local `.venv` by `uv`; nothing is installed globally.

## One-time setup

```bash
uv sync                  # creates .venv from uv.lock (exact versions)
uv run devkit doctor     # read-only prerequisite check
```

`doctor` checks, and never changes: Python, Copier, git (and whether an identity is configured),
Node and npm against the major version the Web Core profile declares, `uv`, `gh` and its login,
optional tools (Homebrew, fnm, Docker, mise) and whether every `Brewfile` entry is installed.
Required failures exit `1`; warnings do not. To install what the `Brewfile` lists, run
`brew bundle --file=Brewfile` yourself; `devkit` never does.

## Create a project

```bash
uv run devkit new my-app --description "What it does" --output-dir .. --dry-run
uv run devkit new my-app --description "What it does" --output-dir ..
```

This builds from the profile's **published** template at the newest release this devkit supports
(see `src/devkit/profiles.py`), and records that repository's URL and the release tag in the
project's `.copier-answers.yml`. It needs network access and fails with a clear message if the
template repository is not reachable or has no supported release. The template repository is
**private**, so git must be able to authenticate without prompting (`publishing.md`, "Private
repositories"); `devkit` never handles credentials itself.

| Option                    | Meaning                                                              |
| ------------------------- | -------------------------------------------------------------------- |
| `NAME`                    | Becomes the directory and the app name. The template validates the format (Web Core: lowercase letters, digits and single hyphens, up to 64, starting with a letter). The CLI itself only requires a single safe path segment. |
| `--description TEXT`      | One line. The template validates it and supplies its own default when omitted. |
| `--output-dir DIR`        | Existing directory to create `NAME` in. Default: the current directory. |
| `--set NAME=VALUE`        | A template option declared by the profile; repeatable. Web Core: `cache_components=true\|false` (Next.js Cache Components with Partial Prefetching, default `true`). Unknown options are rejected. |
| `--template-ref vX.Y.Z`   | Render a specific release instead of the newest supported one. Releases outside the supported range are refused. |
| `--template PATH`         | **Development:** render a local template checkout as it is on disk (working tree included). See below. |
| `--template URL`          | Use a different template origin, with the same release rules.        |
| `--profile web-core`      | The only available profile. `full-stack` and `native-ios` are reserved and rejected. |
| `--dry-run`               | Prints what would be created and writes nothing.                     |

Exit codes: `0` success, `1` generation or a check failed (destination exists, template
unavailable, template rendering failed), `2` rejected input (invalid answer, unknown option,
unsupported release, reserved profile, unsafe name).

Safety rules: `new` refuses to touch anything that already exists at `OUTPUT_DIR/NAME` (a
directory, an empty directory, a file or a symlink), refuses destinations inside this checkout or
the local template checkout, and never deletes anything. If generation fails midway Copier removes
the directory it created.

Then, in the new project:

```bash
cd ../my-app
git init && git add -A && git commit -m "chore: initial commit"   # needed for upgrades
npm ci
npm run check
```

`devkit new` does not run git, npm or `gh`, and does not create a GitHub repository.

## Develop the template locally (no published repository needed)

```bash
uv run devkit new scratch-app --template ../web-core-template --output-dir ..
uv run devkit new scratch-app --template ../web-core-template --template-ref v0.1.0 --output-dir ..
```

Local mode renders the checkout as it is on disk, so uncommitted edits are included, and says so.
`--template-ref` renders any git ref of that checkout. The project records a home-relative path
(for example `~/src/web-core-template`), so it is for development, not for sharing or upgrading. The
template repository has its own end-to-end tests (`uv run pytest` there).

## Upgrade a project to a newer template release

Upgrades are performed with Copier, from inside the project, and always pin the release:

```bash
git status                         # must be clean; commit or stash first
uv run --project /path/to/developer-platform copier update \
    --vcs-ref v0.1.1 --defaults --skip-answered
git diff                           # review; resolve any <<<<<<< inline conflict markers
npm install                        # regenerate package-lock.json after dependency changes
npm run check
git add -A && git commit -m "chore: update project template to v0.1.1"
```

(`/path/to/developer-platform` is your checkout of this repository.) Choose a release inside the range your devkit supports (`>=0.1.0,<0.2.0` for Web Core at devkit
0.2.0; also in `profiles.py`). Without `--vcs-ref`, Copier takes the newest tag, which may be a
breaking release outside that range. The full guide, including conflict handling, is
`web-core-template/docs/upgrading.md`.

## Tests

```bash
uv run pytest                  # everything here (about 15 s; no network)
uv run pytest -m integration   # only the contract test against a web-core-template checkout
```

The integration test needs `../web-core-template` (or `$WEB_CORE_TEMPLATE`) and skips otherwise.
All other tests use a tiny fixture template built into temporary git repositories, so versioned
sources, an https-style published origin, upgrades, unavailable templates, existing destinations
and failed generation are tested without a published repository or network access. The template
repository tests content and runs `npm ci` and `npm run check` in generated apps.

## Troubleshooting

| Symptom                                              | Cause and fix                                                    |
| ---------------------------------------------------- | ---------------------------------------------------------------- |
| `Template source is unavailable`                     | The origin is unreachable, unpublished, or **private and git has no credentials it can use without prompting**. Run `devkit doctor` (`git credentials`), set up access (`publishing.md`, "Private repositories": `gh auth setup-git`), check the URL in `profiles.py`, or use `--template PATH`. |
| `No supported template release found`               | The origin has no tag inside the supported range. Tag a release (see `publishing.md`). |
| `outside the range this devkit supports`             | Pick a supported release or upgrade devkit.                      |
| `warning: ... no commits` / `uncommitted changes` (local mode) | The project records a throwaway commit; commit and tag the template for upgradable projects. |
| `Destination already exists`                         | Pick another name or `--output-dir`; `devkit` will not overwrite. |
| `Destination repository is dirty` during `copier update` | Commit or stash your changes in the project and retry.       |
| `doctor` reports `node ... generated projects pin 26.x` | Select Node 26 (`fnm use` / `nvm use`) before generating or running checks. |
