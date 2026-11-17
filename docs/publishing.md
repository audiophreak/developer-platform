# Publishing and releases

Releases: **`web-core-template` v0.1.0** and **`developer-platform` v0.2.0** (the platform
supports template releases `>=0.1.0,<0.2.0`). **Both repositories are private.** The template is
published first, because the platform's default mode builds from the published template.

Each repository is published the same way, and a tag is only created after CI is green on the
pushed commit, so a tag never points at an unverified commit. Replace `/path/to/...` with your
checkouts.

## Private repositories

Because the template repository is private, everything that reads it needs git credentials that
work without a prompt: `devkit new`, `copier update`, `copier copy`, and anyone else generating or
upgrading a project.

**How `devkit` authenticates.** It does not handle credentials at all. It runs `git` with prompting
disabled (`GIT_TERMINAL_PROMPT=0`), so git uses whatever credential helper is configured. Credentials
are never read, stored, logged or passed as arguments, and URL credentials are redacted from error
messages. `devkit doctor` reports whether any helper is configured (`git credentials`), without
printing it.

**Ways to give git access** (choose one):

1. **Persistent, recommended:** `gh auth setup-git`. This adds the GitHub CLI as the credential
   helper for `github.com` in your global git configuration, a machine-wide change that only you
   should make. `gh` holds the token in the system keyring.
2. **macOS keychain:** the `osxkeychain` helper that ships with Homebrew's git can store a
   fine-grained personal access token with read access to the template repository (git prompts once).
3. **One command, no configuration change** (used to publish and to run the acceptance test; the
   token goes from the `gh` keyring to git over stdin, never into arguments or logs):

   ```bash
   gh_git() {
     GIT_CONFIG_COUNT=2 \
     GIT_CONFIG_KEY_0='credential.https://github.com.helper' GIT_CONFIG_VALUE_0='' \
     GIT_CONFIG_KEY_1='credential.https://github.com.helper' GIT_CONFIG_VALUE_1='!gh auth git-credential' \
     "$@"
   }
   gh_git uv run devkit new my-app --output-dir ..
   ```

   Set before the process starts: Copier runs git through a library that reads the environment at
   start-up, so variables set later by a wrapper script are not seen.

**Limitations of private repositories**

- Every person or machine that generates or upgrades a project needs a GitHub account with read
  access to the template and one of the setups above. Without it `devkit new` fails with
  "Template source is unavailable" and explains why.
- Generated projects record the private template URL in `.copier-answers.yml`, so `copier update`
  has the same requirement. Their own CI does not need the template; only a CI job that runs
  `copier update` would (it would need a token with read access to the template, not set up).
- On GitHub's Free plan, branch protection rules and some other features are not available for
  private repositories, and private repositories use the plan's Actions minutes allowance.
- Switching a repository to public later changes nothing in the recorded URLs. Switching back to
  private does not retract anything already copied.

## Checked before the first release

- `gh` is logged in as the owner named in `src/devkit/profiles.py`, with the `repo` and `workflow`
  token scopes (pushing `.github/workflows/*.yml` needs `workflow`).
- The published flow was rehearsed against a scratch remote: generation in default mode, the
  recorded origin and tag, `npm ci`, `npm run check`, and an upgrade with a user edit preserved
  (`milestone-release-preparation.md`).
- CI runs the whole test suite on Linux with Python 3.12 and 3.14. For the template that includes
  generating real apps and running `npm ci` and `npm run check` on Linux.

## 1. Release `web-core-template` v0.1.0

```bash
cd /path/to/web-core-template
uv sync --locked
uv run --locked pytest                       # all tests, including real npm builds (Node 26 required)
git status                                   # review every file that will be committed
git var GIT_AUTHOR_IDENT; git var GIT_COMMITTER_IDENT   # confirm the identity (a noreply address)
git add -A
git commit -m "feat: web-core template v0.1.0"
gh repo create audiophreak/web-core-template --private --source . --remote origin   # creates it; pushes nothing
gh_git git push -u origin main               # gh_git is defined above (skip it if git is already configured)
sleep 15; gh run watch "$(gh run list --branch main --limit 1 --json databaseId --jq '.[0].databaseId')" --exit-status
#   CI must pass; if not, fix forward with a new commit and push again (no tag yet)
git tag -a v0.1.0 -m "web-core-template v0.1.0"
gh_git git push origin v0.1.0
gh_git git ls-remote --tags origin           # expect refs/tags/v0.1.0
```

Never move or delete a published tag; fix forward with `v0.1.1`.

## 2. Release `developer-platform` v0.2.0

```bash
cd /path/to/developer-platform
gh_git git ls-remote --tags https://github.com/audiophreak/web-core-template.git   # template reachable with authentication
uv sync --locked
gh_git uv run --locked pytest                # the contract tests now run against the published tag (needs ../web-core-template)
uv run devkit doctor
git status
git var GIT_AUTHOR_IDENT; git var GIT_COMMITTER_IDENT
git add -A
git commit -m "feat: split the template into web-core-template; versioned template sources"
gh repo create audiophreak/developer-platform --private --source . --remote origin
gh_git git push -u origin main
sleep 15; gh run watch "$(gh run list --branch main --limit 1 --json databaseId --jq '.[0].databaseId')" --exit-status
git tag -a v0.2.0 -m "developer-platform v0.2.0"
gh_git git push origin v0.2.0
```

## 3. Acceptance check of the published flow

```bash
cd /path/to/developer-platform
CHECK=$(mktemp -d)
gh_git uv run devkit new release-check --description "Release check" --output-dir "$CHECK"
grep -E '_src_path|_commit' "$CHECK/release-check/.copier-answers.yml"
#   expect: _commit: v0.1.0     _src_path: https://github.com/audiophreak/web-core-template.git
cd "$CHECK/release-check"
git init && git add -A && git commit -m "chore: initial commit"
npm ci && npm run check
```

Remove the temporary directory (`$CHECK`) yourself when finished.

## 4. After publishing

- Branch protection for `main` (require the `CI` checks) needs a paid GitHub plan for private
  repositories; no protection or other repository settings were created.
- Optional follow-up: a platform CI job that checks out the template (needs a read token) and runs
  the contract tests (`WEB_CORE_TEMPLATE=<path>`); today the platform's CI skips them because only
  one repository is checked out.
- For the next template release follow `web-core-template/docs/maintaining.md`; widen the
  supported range in `profiles.py` only for breaking releases.
