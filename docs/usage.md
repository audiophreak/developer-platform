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
| `--set NAME=VALUE`        | A template option or optional feature declared by the profile; repeatable. Web Core: `zod=true\|false` (Zod schema validation, default `false`), `forms=true\|false` (React Hook Form with an example form, default `false`; **requires `zod=true`**, template 0.3.0 or newer), `rest_api=true\|false` (versioned REST API v1 with RFC 9457 errors, default `false`; **requires `zod=true`**, template 0.4.0 or newer), `database=none\|postgres\|supabase` (a local PostgreSQL with migrations and a server-only data layer, default `none`; **requires `zod=true`**, template 0.5.0 or newer), `auth=true\|false` (Better Auth sign-in, a least-privilege database role and a protected API, default `false`; **requires `zod=true`, `rest_api=true` and a `database`**, template 0.6.0 or newer) and `cache_components=true\|false` (Next.js Cache Components with Partial Prefetching, default `true`). Only `true` and `false` are accepted; unknown options are rejected before anything is fetched, and an option the selected release lacks is refused. |
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

## Optional features

Features are chosen with `--set`; the choice is recorded in the project's `.copier-answers.yml` and
kept across upgrades:

```bash
uv run devkit new my-app --set zod=true --dry-run      # preview: shows "Options: zod=true", writes nothing
uv run devkit new my-app --set zod=true --output-dir ..
```

With `zod=true` the project gets the exact-pinned `zod` dependency, a shared schema module in
`src/lib/schemas/` with tests for accepted and rejected input, matching documentation and a
lockfile for exactly that dependency set. With it off (the default) the project is identical to
one from template 0.1.0. A feature needs a template release that has it: `--set zod=true` with
`--template-ref v0.1.0` is refused (Copier would otherwise ignore it silently). To switch a feature
on in an existing project use `devkit upgrade PROJECT --set zod=true`. Booleans are strict in `devkit`
and in the template: only `true`/`false` (and `yes`/`no`, `on`/`off` for raw Copier) are accepted.
`forms=true` (template 0.3.0 or newer) adds React Hook Form with the Zod resolver and a small accessible
example form validated by a shared schema, with DOM tests inside `npm run check`:

```bash
uv run devkit new my-app --set zod=true --set forms=true --output-dir ..
uv run devkit upgrade ../my-app --set forms=true     # on an existing project that already has zod
```

`forms` needs `zod`: `--set forms=true` without `--set zod=true` is rejected by the template before
anything is created (exit 2); it never switches Zod on for you, and devkit does not duplicate that
rule. `--template-ref v0.2.1 --set forms=true` is refused up front because that release has no `forms`.

`rest_api=true` (template 0.4.0 or newer) adds versioned route handlers under `/api/v1` with shared Zod
contracts, RFC 9457 problem-details errors, and handler tests that call the handlers directly. It adds
files only: no dependency and no lockfile change.

```bash
uv run devkit new my-app --set zod=true --set rest_api=true --output-dir ..
uv run devkit new my-app --set zod=true --set forms=true --set rest_api=true --output-dir ..
uv run devkit upgrade ../my-app --set rest_api=true     # on an existing project that already has zod
```

`rest_api` needs `zod` exactly like `forms`: without it the template rejects the request before anything
is created (exit 2), it never switches Zod on for you, and devkit does not duplicate the rule.
`--template-ref v0.3.1 --set rest_api=true` is refused up front because that release has no `rest_api`.

`database=postgres` or `database=supabase` (template 0.5.0 or newer) adds a local PostgreSQL 17 database, plain
SQL migrations, a typed server-only data-access layer, real-database tests and `docs/database.md` (components,
local workflow, migrations, security boundaries and recovery). It is **one choice**, so there is no way to select
two providers, and anything but `none`, `postgres` or `supabase` is refused before a template is read:

```bash
uv run devkit new my-app --set zod=true --set database=postgres --output-dir ..    # Docker Compose
uv run devkit new my-app --set zod=true --set database=supabase --output-dir ..    # local Supabase stack
uv run devkit upgrade ../my-app --set database=postgres   # enable it on an existing project that has zod
```

`database` needs `zod` like `forms` and `rest_api`: without it the template rejects the request before anything
is created (exit 2), it never switches Zod on, and devkit does not duplicate the rule. It does not enable Forms
or the REST API, and the generated project has no route that touches the database (authentication does not exist
yet). Local development only.

**An established provider is not changed by `upgrade`.** Once a project has `postgres` or `supabase`,
`devkit upgrade --set database=<another value>`, including `none`, is refused with exit 2 and nothing is
touched: the change would swap the tooling under existing data, and moving data between databases is not
automated. Generate a new project with the other provider and move your data deliberately (see the generated
`docs/database.md`). Naming the provider the project already has is fine, and so is upgrading without naming it.
Raw `copier update` has no such protection (a Copier validator cannot see the previous answer): it silently
swaps the tooling, so use `devkit upgrade`.

`auth=true` (template 0.6.0 or newer) adds Better Auth email/password authentication with sessions in PostgreSQL, a
least-privilege `app_runtime` database role for the running application, owner-scoped data protected by row level
security, a protected `/api/v1/items` API, real-database tests and `docs/auth.md`. It works the same on both
database providers (Supabase Auth is not used):

```bash
uv run devkit new my-app --set zod=true --set rest_api=true --set database=postgres --set auth=true --output-dir ..
uv run devkit new my-app --set zod=true --set rest_api=true --set database=supabase --set auth=true --output-dir ..
uv run devkit upgrade ../my-app --set auth=true   # on an existing project that has zod, rest_api and a database
```

`auth` needs `zod`, `rest_api` and a `database`: if any is missing the template rejects the request before anything is
created or changed (exit 2), nothing is switched on for you, and devkit does not duplicate the rules. `forms` is
independent. The generated project is ready for local development and integration testing, **not for open
registration on the public internet**: email verification, password-reset delivery, trusted-proxy and origin
configuration are the deployer's to provide (the generated `docs/auth.md` lists them). After enabling it on an
existing project run `npm ci`, `npm run db:init` (it appends the new settings to your `.env.local` and changes
nothing else) and `npm run db:migrate`.

**Upgrading a Supabase project that has already run its local stack:** the CLI creates `supabase/.temp` and
`supabase/.branches`, which templates before 0.6.0 did not ignore, and `upgrade` needs a clean working tree. Add those two
paths to the project's `.gitignore` and commit it before upgrading (new projects from 0.6.0 ignore them already).

**Established authentication is not removed by `upgrade`.** Once a project has `auth=true`,
`devkit upgrade --set auth=false` is refused with exit 2 and nothing is touched: removing it would orphan accounts and
data ownership, and a script must not decide that for you (see the generated `docs/auth.md` for the manual steps).
Naming `auth=true` again is fine, and so is upgrading without naming it.
How features work: `feature-composition.md`; what is planned: `full-stack-plan.md`.

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

```bash
uv run devkit upgrade ../my-app --dry-run     # the plan and Copier's preview; changes nothing
uv run devkit upgrade ../my-app               # upgrade to the newest release this devkit supports
uv run devkit upgrade ../my-app --to v0.2.0   # or to a specific supported release
uv run devkit upgrade ../my-app --set zod=true   # change an option or feature while upgrading
```

What it does, and refuses:

- It reads the project's recorded template origin and release (`.copier-answers.yml`) and requires
  the release to be a plain tag inside the range this devkit supports (`>=0.1.0,<0.7.0` for Web Core
  at devkit 0.7.0). A project from an older or newer release, or from commits after a release,
  is refused with an explanation.
- The project must be the root of a git repository with **nothing uncommitted** (no modified and no
  untracked files). Otherwise it refuses and changes nothing, so your work can never mix with the
  upgrade and is always recoverable.
- The target is the newest supported release newer than the installed one (`--to` to choose);
  downgrades, unpublished releases and releases outside the range are refused. A project that is
  already current is reported as such.
- **Your feature selections are kept** (recorded answers are reused); features a newer release
  introduces stay off unless you pass `--set`. An option the target release does not have is refused.
- Copier merges the new release into your files. Your own changes are merged, never overwritten.
  Where both sides changed the same lines, both are kept between `<<<<<<<` and `>>>>>>>` markers and
  the command exits **3** naming the files; nothing is deleted. Fix them, `git add`, commit.
- It never commits. Afterwards: `git diff`, `npm ci` (the template ships a lockfile for your
  selection), `npm run check`, then commit. Work on a branch if you want an easy way back.
- A project generated in local development mode (`--template PATH`) can be upgraded from that
  checkout, with a warning that its origin is not published.

Exit codes: `0` upgraded, already current, or previewed; `1` the project or origin cannot be
upgraded safely (dirty, not a git root, unavailable origin, unreleased version); `2` rejected
arguments or an unsupported transition; `3` upgraded with conflicts to resolve. Direct `copier
update` still works, but it takes the newest tag whatever this devkit supports; always pin
`--vcs-ref` (the template's `docs/upgrading.md`).

## Tests

```bash
uv run pytest                  # everything here (about 30 s; no network, no credentials)
uv run pytest -m integration   # the live checks against a web-core-template checkout
```

Compatibility with every supported template release is tested **offline**:
`tests/contracts/web-core/<version>.json` are snapshots of each release's questions (types, defaults,
choices) and Node major, captured from release tags by `tools/capture_contract.py`, and
`tests/test_contract_snapshots.py` checks the profile registry against all of them. This runs in CI.
The **release gate** is separate and needs the template checked out (`../web-core-template`, or
`$WEB_CORE_TEMPLATE`): `uv run pytest -m integration` proves each snapshot still equals the real
template (a tag, or the working tree for the newest unreleased version) and that old and new releases
really generate; it skips without a checkout. All other tests use small fixture templates built into
temporary git repositories, so versioned sources, an https-style origin, upgrades, unavailable
templates, existing destinations and failed generation need no published repository. The template
repository tests content and runs `npm ci` and `npm run check` in generated apps.

To re-capture a snapshot (when a release is tagged): `uv run python tools/capture_contract.py
--template ../web-core-template --ref v0.2.0 --write`; `--check` verifies it.

## Scratch space and cleanup

Never delete by hand. `uv run python tools/scratch.py new` prints a fresh, marked workspace under the
system temporary directory; `uv run python tools/scratch.py clean WORKSPACE [CHILD...]` removes only
paths provably inside a workspace it created (it refuses symlinks, `..` escapes, `/`, the home
directory and the current directory). A test fails if code or documented snippets contain recursive
deletes, `git clean`, `git reset --hard` or forced pushes.

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
