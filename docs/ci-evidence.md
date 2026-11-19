# CI test evidence

Every CI run uploads a small, machine-readable record of what was tested, so that a result can be
checked independently of the console log. Nothing here changes whether the build passes: the job
still fails exactly when pytest fails.

## What a run produces

One artifact per Python version (3.12 and 3.14), named `test-reports-py<version>-<commit>`, where
`<commit>` is the full SHA of the commit under test. It is uploaded **even when the tests fail**, and
kept for **30 days**.

| File | Contents |
| ---- | -------- |
| `junit.xml` | JUnit XML written by pytest. The `testsuite` name is `developer-platform@<commit>-py<version>`; its `tests`, `failures`, `errors` and `skipped` attributes are the counts; every `testcase` has a `failure`, `error` or `skipped` child (with the message or the skip reason) when it did not pass. Captured output is not included. |
| `pytest-output.txt` | The complete console output, including the short summary of every failure, error and skip with its reason. |
| `metadata.txt` | `commit_under_test`, `github_sha`, `ref`, `event`, `run_id`, `run_attempt`, `runner_os`, the Python, `uv` and pytest versions, and the SHA-256 of `uv.lock`. |
| `installed-packages.txt` | The exact package versions installed for that run (`uv pip freeze`, without the editable project). |

The same run also writes a **job summary** (the last 60 lines of the console record, which hold the
pass, fail and skip counts and the reasons) on the run's page.

**Which commit?** On a pull request, GitHub tests a synthetic merge of the branch into `main`
(`github_sha`). The evidence is tied to the *branch tip you reviewed* instead: `commit_under_test`,
which is also in the artifact and suite names. Both are recorded.

## Retrieving it

On the run's page, the artifacts are listed at the bottom. From a terminal (needs your existing `gh`
login; use a fresh empty directory, for example from `uv run python tools/scratch.py new`):

```bash
gh run list --commit <full-sha>                       # find the run for a commit
gh run download <run-id> --dir <empty-directory>      # every artifact of the run, one folder each
gh run download <run-id> --name test-reports-py3.14-<full-sha> --dir <empty-directory>
```

## Reading it

```python
import sys, xml.etree.ElementTree as ET

suite = ET.parse(sys.argv[1]).getroot()
suite = suite if suite.tag == "testsuite" else suite.find("testsuite")
print({k: suite.get(k) for k in ("name", "tests", "failures", "errors", "skipped")})
for case in suite.iter("testcase"):
    for kind in ("failure", "error", "skipped"):
        found = case.find(kind)
        if found is not None:
            print(kind, case.get("classname"), case.get("name"), (found.get("message") or "")[:100])
```

A green run shows `failures="0" errors="0"`. Compare `commit_under_test` with the commit you are
reviewing, and `uv_lock_sha256` with `sha256sum uv.lock` at that commit.

## Skipped tests

The tests marked `integration` skip in CI: those in `tests/test_integration_web_core.py` with the reason "no
web-core-template checkout", those in `tests/test_integration_native_ios.py` with "needs checkouts of
web-core-template and native-ios-template". At devkit 0.8.x that is 28 tests (26 web, 2 native pair); `uv run pytest
--collect-only -q -m integration` prints the current number. They compare the platform with the real private
templates and are the **local release gate** (`uv run pytest -m integration`, run where both templates are checked
out beside this repository, or at `$WEB_CORE_TEMPLATE` and `$NATIVE_IOS_TEMPLATE`). They are skipped,
not deleted, because running them in CI would need a credential able to read the private template
repositories, which this project deliberately does not store. Offline contract snapshots cover
compatibility in CI (`release-strategy.md`, section 6). The skips are visible in `junit.xml` and the
summary on every run.

## Negative control: the failure probe

The evidence workflow was proven to report a red run correctly, not only green ones. On 2026-11-17 a probe commit added
`tests/test_zz_ci_probe.py` with one deliberately failing test (`assert 1 + 1 == 3`) and one deliberately skipped test
(reason "deliberate probe skip: must appear with this reason in junit.xml"), on a branch `probe/ci-evidence-failure`
opened as a pull request titled "PROBE (do not merge): deliberate CI failure":

| | |
|---|---|
| Probe commit | `8a3b8d1333c389b857c24dea03729589ce62c438` |
| Pull request | #3, closed without merging |
| CI run | `44118456812`, conclusion **failure** on both Python versions (3.12 and 3.14), as intended |

It showed that a failing run still uploads its evidence and that the failure and the skip, with its reason, appear in
`junit.xml` and the job summary. The commit was never merged into `main`. The branch was deleted from GitHub after the
probe; the commit remains reachable there through the closed pull request (`refs/pull/3/head`), and the local branch ref
was removed in the 0.8.1/0.7.1 documentation closeout once this record existed.

## Security

- The workflow keeps `contents: read`, pinned actions and no secrets. Artifact upload uses the
  runner's own scoped token, not a repository credential.
- Reports are generated by pytest and a few shell lines that write named fields; **nothing dumps the
  environment**, and JUnit logging is off. Test failure messages can quote test data, so treat
  artifacts as repository-internal: in a private repository they are visible to people who can read it.
- Before upload, the reports are scanned for token-shaped strings (GitHub tokens, private-key
  headers, AWS key ids) with a **quiet** `grep -q`: the matching text is never printed. A hit, or a
  scan that cannot run, fails the job with a generic error and **skips the upload**. The job summary
  is written only after the scan passes. A regression test runs the workflow's own scan on fake
  credentials in a disposable directory and checks that it rejects them without printing them.
- A test (`tests/test_ci_workflow.py`) fails if the workflow stops uploading on failure, drops the
  scan, widens the artifact path, extends retention beyond 30 days, adds a credential, or dumps the
  environment.

## Limitations

- **The scan protects the artifact, not the log.** Test output is shown live in the job log while
  pytest runs (`tee`), before any scan can run; a secret that a test prints would be in that log
  regardless. GitHub masks only secrets it knows (registered secrets), and this project stores none.
  The rule is: tests must never print credentials. The scan is a backstop for the uploaded files.
- The scan recognizes a few common shapes, not every secret, and does not decode or unpack anything.
- This is evidence, not attestation: anyone who can change the workflow can change what it reports,
  and nothing signs the artifacts. Branch protection (not enabled) would make review of workflow
  changes mandatory.
- Artifacts expire after 30 days; the console log expires on GitHub's own schedule. Keep a copy of
  the evidence you need for a release record.
- No coverage or security-analysis reports are collected.
