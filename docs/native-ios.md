# Full-stack and native iOS profiles (devkit 0.8.0)

Three profiles are available. `web-core` is unchanged. The other two are **compositions**, not new technologies.

| Profile | What it generates | What you must say |
|---|---|---|
| `web-core` | the Web Core template; features are optional (`--set zod=true` ...) | nothing |
| `full-stack` | Web Core with `zod`, `rest_api` and `auth` always on, plus a database | `--set database=postgres` or `database=supabase` |
| `native-ios` | `full-stack` with `native_client` on, **plus the native iOS layer** in `ios/` | the same database choice |

`zod`, `rest_api`, `auth` (and `native_client` for `native-ios`) are *part of what the profile is*: naming one with another value
is refused, naming it with the same value is fine. **The database provider is never defaulted**: it is an architectural
choice, so `devkit new --profile full-stack NAME` without it is an error that lists the choices. `forms` stays optional.

```sh
devkit new my-app --profile full-stack --set database=postgres [--set forms=true]
devkit new my-app --profile native-ios --set database=supabase \
    --native-set bundle_identifier=com.acme.myapp --native-set release_api_host=api.acme.com
```

## Two templates, one directory

`native-ios` applies **two independent Copier templates** to one project directory:

| Layer | Template | Owns | Answers file | Releases |
|---|---|---|---|---|
| web | `web-core-template` | everything except `ios/` | `.copier-answers.yml` | `v0.7.x` here |
| native | `native-ios-template` | `ios/` only | `.copier-answers.ios.yml` | `v0.1.x` here |

Neither template writes the other's files (tests prove it in both directions), and each records its own source and
release, so `devkit status` can name them separately. The web template knows only that an `ios/` directory *may* exist (it
excludes it from its own lint and format checks and tells agents to read `ios/AGENTS.md`); it knows nothing of devkit.
The native template knows the contract of the web release it was generated from (`ios/Contract/openapi.json`), which a test
compares with the web project's own `openapi/openapi.json`.

**Which pairs belong together** is data in `profiles.py` (`NATIVE_REQUIRES_WEB`): native 0.1.x works with web `>=0.7.0,<0.8.0`.
`devkit new` refuses a pair outside it before writing anything; `upgrade` refuses a step that would break it.

## Safety of building both layers

With the native layer, `devkit new` builds the web layer and then the native layer in a hidden staging directory next to the
destination, and moves it into place only when both succeeded. A failure leaves **nothing** at the name you asked for, and
the partial result at `.NAME.devkit-partial` for you to inspect (devkit never deletes it, and refuses to run again until you
have). `--dry-run` writes nothing for either layer.

## Adding the native layer later

`devkit native add PROJECT` applies the native layer to a project that is already full-stack. It requires a committed, clean
git tree, the baseline (`zod`, `rest_api`, `auth`, a database) and `native_client` already on. If `native_client` is off it
stops and tells you to run `devkit upgrade PROJECT --set native_client=true`, review and commit, then retry: devkit does not
switch a feature on for you. It adds `ios/` and `.copier-answers.ios.yml` and changes none of your files.

## Upgrading the two layers

A project with two layers is upgraded **one layer at a time**:

```sh
devkit status PROJECT                        # both layers, their releases, what is newer
devkit upgrade PROJECT --layer web  [--to vX.Y.Z] [--dry-run]
devkit upgrade PROJECT --layer native [--to vX.Y.Z] [--dry-run]
```

- `devkit upgrade PROJECT` without `--layer` is refused in a two-layer project: it will not guess.
- Each upgrade needs a clean git tree, so it is reviewed and **committed on its own** before the next one; one layer's changes
  can never hide inside the other's.
- After upgrading one layer, devkit says the project is **not fully upgraded** while the other layer has a newer release, and
  `devkit status` keeps saying it (exit 1 if the two installed releases do not belong together).
- An upgrade that would leave the pair outside `NATIVE_REQUIRES_WEB` is refused with the reason. A merge conflict in one layer
  is reported (exit 3) and the other layer is untouched.
- Raw `copier update` is **not** safe here by default: without `--answers-file .copier-answers.ios.yml` it reads the web
  layer's answers. Use devkit, or pass the file.

## What the native layer needs from the web part

`auth=true` and `native_client=true` (bearer tokens for native clients and the OpenAPI 3.1 contract of `/api/v1`). Both are in
the `native-ios` profile by definition. The iOS app itself needs Xcode 26+ and an iOS Simulator runtime to build and test; see
the generated `ios/README.md`.
