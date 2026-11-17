# Feature composition: decision record

How optional application features are represented, selected, enforced, locked, recorded and
upgraded. Implemented for one feature (Zod) in `web-core-template` 0.2.0 and `devkit` 0.3.0;
the roadmap for the rest is `full-stack-plan.md`, versions and upgrades are in
`release-strategy.md`, and the template-side mechanics are in that repository's
`docs/features.md`.

## Decision in one table

| Question | Decision |
| -------- | -------- |
| 1. Representation and selection | One **boolean Copier question per feature** (default off), in a strict form. `features.yml` in the template repository declares requires/conflicts and which features change npm dependencies. Selected with `devkit new --set NAME=true` or `copier --data`. |
| 2. Is Copier conditional rendering enough? | **Yes** for additive features: conditional file names, conditional blocks, computed values and an include-based lockfile shim all work. Add-on templates are the escape hatch for features with their own toolchain or cadence (native iOS), not needed before then. |
| 3. Dependencies and incompatibilities | Rules in `features.yml`; enforced at generation by **validators in `copier.yml`** (covers every front-end); enumerated and tested over the whole supported matrix. Booleans are strict in the template itself, so `devkit` and raw Copier behave identically. |
| 4. Exact versions and lockfiles | Exact pins written once in `package.json.jinja`. **One committed lockfile per distinct npm dependency set** in `locks/`, derived from the base lock by a maintainer tool and verified by tests. No resolution at generation. |
| 5. Recording and upgrades | The answers file records selections; `copier update` reuses them. Switching a feature on later works through `copier update --data`; switching off is manual. |
| 6. Future features without duplication | Features are additive modules in one template, sharing `src/lib/schemas` as the contract between forms, API and clients; native iOS becomes a separate add-on template consuming a generated API contract. |
| 7. Repository boundary | **No change.** The platform declares options (with defaults) and the supported template range; the template knows nothing about the platform; a contract test links them. |

## 1. Representation and selection

A feature is a Copier boolean question named like the feature, a `features.yml` entry, its files
and blocks, and tests that ship inside the generated project and run in `npm run check`.

```
devkit new my-app --set zod=true            # strict: only true or false are accepted
copier copy --data zod=true ...             # raw Copier: booleans are strict too
```

Answers are the right unit: they are what Copier records, validates, prompts for, merges on update
and shows in `--dry-run`. Choices (a database provider) will be `choices:` questions that are only
asked `when:` their parent feature is on.

**A hazard found while testing, and its fix.** Copier casts a `type: bool` answer *before* validators
run, so `--data zod=banana` silently enabled the feature and no validator could reject it. Tested
alternatives (all with the same inputs through the Python API and the real command line):

| Representation | `banana` | `1`, `0`, empty, null | `yes`/`no`/`on`/`off` | Recorded as |
| -------------- | -------- | --------------------- | --------------------- | ----------- |
| `type: bool` | accepted as true | accepted | accepted | boolean |
| `type: yaml` + `choices` | rejected | `1`/`0` accepted (recorded as integers) | accepted | boolean |
| `type: yaml` + `is boolean` validator | rejected | rejected | accepted | boolean |
| `type: str` + `choices: ["false","true"]` | rejected | rejected | rejected | **string** (breaks existing answers) |
| **`yaml` + `choices` + validator** (adopted) | rejected | rejected | accepted | boolean |

The adopted form works identically through `devkit` and raw Copier with one copy of the rule (in
`copier.yml`), gives an interactive select list, and records real booleans, so projects generated
with the old questions upgrade cleanly (tested). `devkit --set` additionally accepts only
`true`/`false`.

## 2. Is Copier conditional rendering sufficient?

Tested in a scratch template before any design was fixed:

| Mechanism needed | Result |
| ---------------- | ------ |
| Skip a feature's files when off | A path whose name renders empty is skipped with everything under it; no empty directories are left (verified on the default output). |
| Conditional blocks in shared files | Work; whitespace must be exact, so a release tool proves default output is byte-identical to the previous tag. |
| Select one of several lockfiles | A one-line `{% include "locks/" ~ lock_key ~ ".json" %}` shim works. The Jinja search path is the **repository root**, not the rendered `_subdirectory`, so lockfiles live in a top-level `locks/` that is never rendered. |
| A value derived from answers, not recorded | A `when: false` question with a Jinja default is available to templates and absent from the answers file. |
| Run nothing at generation | Satisfied: no tasks, migrations, extensions or installs. |

**Where it stops being enough.** Conditionals in shared files interleave features, and lockfiles do
not compose. Treat these as the limits:

- **Matrix size.** Lockfiles needed = distinct npm dependency sets (not 2^features), about 400 KB
  each. A test caps the matrix at 16. Beyond that, replace "every valid subset" with a short list of
  declared presets.
- **Separate toolchain or cadence.** A feature with its own build system (an Xcode project) or its
  own release rhythm should be an **add-on template** applied to the same directory with its own
  answers file (Copier supports several per project) and versions. This is a hypothesis: layering
  has not been prototyped, and it does not solve npm lockfiles (an app has one lock), so any layer
  that adds npm dependencies still joins the matrix.
- **Divergent forks** (two incompatible implementations of one thing) should be separate profiles,
  not a feature flag.

A more elaborate engine (a code generator, a package-manager workspace per feature) would add
infrastructure for problems the matrix does not have yet.

## 3. Dependencies and incompatibilities

```yaml
# features.yml (tooling and tests)            # copier.yml (enforced at generation)
forms:                                         forms:
  requires: [zod]                                validator: "{% if forms and not zod %}..."
```

Three layers, each catching a different failure:

1. **`copier.yml` validators** are authoritative: any front-end that renders the template hits them,
   and Copier fails before writing anything. Questions are asked in order, so prerequisites come
   first.
2. **`devkit --set`** parses types strictly and rejects unknown options before any network access,
   because the profile registry declares the options. Rule checks stay in the template so there is
   one copy of each rule.
3. **Tests** enumerate the whole supported matrix from `features.yml` (`tools/features.py`), render
   every valid configuration, assert a validator exists for every rule, and cover requires,
   conflicts, chains, cycles and unknown references with synthetic registries. (No real rule
   exists yet, because `zod` has no prerequisite, so the parity check is exercised structurally and
   the rule logic only through the synthetic registries until `forms` arrives.)

Not chosen: auto-selecting prerequisites. It hides what a project contains; failing with "forms
requires zod" keeps the selection explicit and recorded.

## 4. Exact versions and lockfiles for every configuration

Versions are written once, in `package.json.jinja`, as exact pins of releases at least two weeks
old. Each distinct dependency set has a complete committed lockfile (`locks/<key>.json`) selected by
a computed key.

How a feature lockfile is made (`tools/refresh_locks.py`): render the configuration to get its exact
`package.json`; start npm from the **base lockfile**; let npm add only what the new dependency needs
(`--package-lock-only --ignore-scripts`, with `--before` set to two weeks ago so new transitive
packages obey the age rule); refuse to write unless the result is strictly additive (every base
package unchanged in version, source and hash). Tests re-check this for every lockfile, plus:
registry-only sources with integrity hashes, matching `package.json`, no orphan files, and **no new
install scripts**.

Rejected alternatives:

| Alternative | Why not |
| ----------- | ------- |
| `npm install` after generation | Uncontrolled resolution at the user's machine; breaks reproducibility and the age rule; the milestone forbids it. |
| Merge per-feature lock fragments at generation | npm's tree (hoisting, dedup) does not merge reliably. |
| One lock containing every feature's dependencies | Ships unused packages, and their attack surface, into every project. |
| A workspace per feature | Heavy structure for a single-app template. |

The real example is informative: Zod is already in the base lock as a development-only transitive
dependency of the shadcn CLI, at the same version, so the Zod lockfile differs from the base by two
lines (a root dependency and the removal of a `dev` flag). Many features will be similarly small;
growth comes from the number of distinct dependency sets, which is why docker or configuration
features that add no npm dependency share the base lock.

## 5. Recording selections and upgrades

`.copier-answers.yml` records `zod: true`; the computed `lock_key` is never recorded. Verified by
tests with a bare repository standing in for the published template:

- an upgrade keeps the selection, merges template changes into feature files, and leaves the user's
  own files (a schema they added beside the template's) untouched;
- a project without the feature stays without it, including its lockfile;
- switching a feature on later: `copier update --vcs-ref <tag> --data zod=true` adds the files, the
  dependency and the matching lockfile with no conflicts (verified for a project with user edits);
- not automated: switching off (delete the files and dependency by hand, or regenerate).

Changing the *dependency set* of an existing project replaces its lockfile by a three-way merge. It
merged cleanly in the tested case; documented fallback: resolve `package.json`, then `npm install`.

## 6. Supporting future features without duplication

- **One module per feature, additive.** A feature adds files under conditionally named
  directories, a few dependency lines and short blocks in shared files; it never copies shared
  files. Shared files carry only guarded blocks.
- **`src/lib/schemas` is the contract.** Forms (client), route handlers (server) and the iOS client
  (through a generated API description) all derive from the same Zod schemas, so a rule is written
  once. This is why Zod is the first feature: everything after it depends on it.
- **Server code is separated by directory and enforced by tests** (`src/server`, `server-only`),
  not by convention (details in `full-stack-plan.md`).
- **Native iOS is an add-on template**, not part of this matrix: different toolchain, owner and
  release cadence; it consumes an API contract the web app publishes.
- **Cross-cutting edits stay small.** If a feature needs more than a few guarded lines in a shared
  file, extract a stable extension point in the previous release first.

## 7. Does the platform/template boundary change?

No. The existing one-way contract is extended in two small ways:

- The registry now also declares each option's **default**, and a contract test checks it equals the
  template's default (so the documented behaviour cannot drift from the real one).
- Options declare the release they first appear in (`since`), so one `devkit` can support several
  template lines: devkit 0.3.0 supports `>=0.1.0,<0.3.0`, and refuses `--set zod=true` for 0.1.x.

`devkit` still does not read `features.yml`: it declares options, the template enforces rules.
Revisit if the option list grows enough that the duplication hurts; the likely answer is a small
neutral options manifest published by the template, read in local mode and by CI.

## Tradeoffs accepted

| Choice | Cost | Why acceptable |
| ------ | ---- | -------------- |
| Committed lockfile per dependency set | Repository size; a refresh step | Reproducible and reviewable; capped by a test; no resolution at generation. |
| Rules written in `features.yml` and `copier.yml` | Two places per rule | A parity test fails on drift; validators are the only thing that protects every front-end. |
| Registry options duplicated in `devkit` | Two places per option | Fast, offline, typed validation; guarded by the contract test. |
| Selections cannot be switched off automatically | Manual removal | Safer than deleting a user's files; rare. |
| A boolean needs `type: yaml` + choices + a validator | Slightly unusual `copier.yml` | Fixed in the template (strict form); pinned by tests. |
