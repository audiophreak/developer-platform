from __future__ import annotations

import contextlib
import dataclasses
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from devkit import profiles

PLATFORM_ROOT = Path(__file__).resolve().parents[1]
MINI_TEMPLATE = Path(__file__).resolve().parent / "fixtures" / "mini_template"
MINI_NATIVE = Path(__file__).resolve().parent / "fixtures" / "mini_native"
HTTPS_ORIGIN = "https://example.invalid/acme/web-core-template.git"

# Hermetic git identity so tests never read (or depend on) the machine's git configuration.
GIT_TEST_ENV = {
    "GIT_AUTHOR_NAME": "Test User",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test User",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def run_git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_TEST_ENV},
        check=True,
    )
    return result.stdout


def make_template_repo(destination: Path, releases: tuple[str, ...] = ()) -> Path:
    """The mini template as a committed git repo, with one tagged commit per release.

    Each release writes its version (without the leading "v") into version.txt.
    """
    destination.mkdir(parents=True)
    shutil.copy2(MINI_TEMPLATE / "copier.yml", destination / "copier.yml")
    shutil.copytree(MINI_TEMPLATE / "template", destination / "template")
    run_git(destination, "init", "-q", "-b", "main")
    run_git(destination, "add", "-A")
    run_git(destination, "commit", "-q", "-m", "initial")
    for tag in releases:
        release(destination, tag)
    return destination


def release(repo: Path, tag: str, **files: str) -> None:
    """Commit a change (version.txt plus any `files`, keyed by template-relative path) and tag it."""
    (repo / "template" / "version.txt").write_text(tag.lstrip("v") + "\n")
    for relative, content in files.items():
        target = repo / "template" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", f"release {tag}")
    run_git(repo, "tag", tag)


ZOD_QUESTION = "\nzod:\n  type: bool\n  default: false\n"
FORMS_QUESTION = (
    "\nforms:\n  type: bool\n  default: false\n  validator: >-\n"
    "    {% if forms and not zod %}forms requires zod: answer zod=true as well "
    "(forms is never enabled for you).{% endif %}\n"
)
FLAGS_WITH_ZOD = "cache_components={{ cache_components | lower }}\nzod={{ zod | lower }}\n"
FLAGS_WITH_FORMS = FLAGS_WITH_ZOD + "forms={{ forms | lower }}\n"
REST_API_QUESTION = (
    "\nrest_api:\n  type: bool\n  default: false\n  validator: >-\n"
    "    {% if rest_api and not zod %}rest_api requires zod: answer zod=true as well "
    "(rest_api is never enabled for you).{% endif %}\n"
)
FLAGS_WITH_REST_API = FLAGS_WITH_FORMS + "rest_api={{ rest_api | lower }}\n"
DATABASE_QUESTION = (
    "\ndatabase:\n  type: str\n  default: none\n  choices: [none, postgres, supabase]\n  validator: >-\n"
    "    {% if database != 'none' and not zod %}database requires zod: answer zod=true as well "
    "(database is never enabled for you).{% endif %}\n"
)
FLAGS_WITH_DATABASE = FLAGS_WITH_REST_API + "database={{ database }}\n"
AUTH_QUESTION = (
    "\nauth:\n  type: bool\n  default: false\n  validator: >-\n"
    "    {% if auth and not zod %}auth requires zod: answer zod=true as well (auth is never enabled for you)."
    "{% elif auth and not rest_api %}auth requires rest_api: answer rest_api=true as well (auth is never enabled for you)."
    "{% elif auth and database == 'none' %}auth requires a database: answer database=postgres or database=supabase as well "
    "(auth is never enabled for you).{% endif %}\n"
)
FLAGS_WITH_AUTH = FLAGS_WITH_DATABASE + "auth={{ auth | lower }}\n"
NATIVE_CLIENT_QUESTION = (
    "\nnative_client:\n  type: bool\n  default: false\n  validator: >-\n"
    "    {% if native_client and not auth %}native_client requires auth: answer auth=true as well "
    "(native_client is never enabled for you).{% endif %}\n"
)
FLAGS_WITH_NATIVE_CLIENT = FLAGS_WITH_AUTH + "native_client={{ native_client | lower }}\n"
FLAGS_WITHOUT_ZOD = "cache_components={{ cache_components | lower }}\n"


def make_versioned_template(
    destination: Path,
    *,
    through_forms: bool = False,
    through_rest_api: bool = False,
    through_database: bool = False,
    through_auth: bool = False,
    through_native: bool = False,
) -> Path:
    """A mini template whose releases mirror the real one: v0.1.x has no `zod` question, v0.2.x has
    `zod`, v0.3.x adds `forms` (which requires zod, enforced by the template's own validator).

    v0.4.x adds `rest_api` (which also requires zod). Releases: v0.1.0, v0.1.1, v0.2.0, v0.2.1, with
    `through_forms` also v0.3.0 and v0.3.1, with `through_rest_api` also v0.4.0 and v0.4.1, and with
    `through_database` also v0.5.0 and v0.5.1 (v0.5.x adds `database`, which also requires zod), and with
    `through_auth` also v0.6.0 and v0.6.1 (v0.6.x adds `auth`, which requires zod, rest_api and a database). Each
    writes its version into version.txt. Without the flags the history stops at the earlier line, so
    tests written for it keep cutting later releases from that state.
    """
    full = (MINI_TEMPLATE / "copier.yml").read_text()
    assert ZOD_QUESTION in full and FORMS_QUESTION in full and REST_API_QUESTION in full and DATABASE_QUESTION in full
    assert AUTH_QUESTION in full and NATIVE_CLIENT_QUESTION in full
    destination.mkdir(parents=True)
    shutil.copytree(MINI_TEMPLATE / "template", destination / "template")

    def write(copier_yml: str, flags: str) -> None:
        (destination / "copier.yml").write_text(copier_yml)
        (destination / "template" / "flags.txt.jinja").write_text(flags)

    without_native = full.replace(NATIVE_CLIENT_QUESTION, "")
    without_auth = without_native.replace(AUTH_QUESTION, "")
    without_database = without_auth.replace(DATABASE_QUESTION, "")
    without_rest_api = without_database.replace(REST_API_QUESTION, "")
    without_forms = without_rest_api.replace(FORMS_QUESTION, "")
    write(without_forms.replace(ZOD_QUESTION, ""), FLAGS_WITHOUT_ZOD)
    run_git(destination, "init", "-q", "-b", "main")
    run_git(destination, "add", "-A")
    run_git(destination, "commit", "-q", "-m", "initial")
    release(destination, "v0.1.0")
    release(destination, "v0.1.1")
    write(without_forms, FLAGS_WITH_ZOD)
    release(destination, "v0.2.0")
    release(destination, "v0.2.1")
    if through_forms or through_rest_api or through_database or through_auth or through_native:
        write(without_rest_api, FLAGS_WITH_FORMS)
        release(destination, "v0.3.0")
        release(destination, "v0.3.1")
    if through_rest_api or through_database or through_auth or through_native:
        write(without_database, FLAGS_WITH_REST_API)
        release(destination, "v0.4.0")
        release(destination, "v0.4.1")
    if through_database or through_auth or through_native:
        write(without_auth, FLAGS_WITH_DATABASE)
        release(destination, "v0.5.0")
        release(destination, "v0.5.1")
    if through_auth or through_native:
        write(without_native, FLAGS_WITH_AUTH)
        release(destination, "v0.6.0")
        release(destination, "v0.6.1")
    if through_native:
        write(full, FLAGS_WITH_NATIVE_CLIENT)
        release(destination, "v0.7.0")
        release(destination, "v0.7.1")
    return destination


def make_native_repo(destination: Path, releases: tuple[str, ...] = ("v0.1.0", "v0.1.1")) -> Path:
    """The mini native template as a committed git repo; each release writes its version into ios/version.txt."""
    destination.mkdir(parents=True)
    shutil.copy2(MINI_NATIVE / "copier.yml", destination / "copier.yml")
    shutil.copytree(MINI_NATIVE / "template", destination / "template")
    run_git(destination, "init", "-q", "-b", "main")
    run_git(destination, "add", "-A")
    run_git(destination, "commit", "-q", "-m", "initial")
    for tag in releases:
        (destination / "template/ios/version.txt").write_text(tag.lstrip("v") + "\n")
        run_git(destination, "add", "-A")
        run_git(destination, "commit", "-q", "-m", f"release {tag}")
        run_git(destination, "tag", tag)
    return destination


def make_remote(repo: Path, destination: Path) -> Path:
    """A bare clone standing in for a published repository."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_git(destination.parent, "clone", "-q", "--bare", str(repo), str(destination))
    return destination


def publish(repo: Path, remote: Path, *refs: str) -> None:
    run_git(repo, "push", "-q", str(remote), "main", *refs)


@pytest.fixture()
def point_profile_at(monkeypatch: pytest.MonkeyPatch):
    """Make the web-core profile build from `url`, supporting `versions` (an inclusive-low,
    exclusive-high pair of tuples). Returns the replaced profile."""

    def apply(url: str, versions=((0, 1, 0), (0, 2, 0))):
        profile = profiles.PROFILES["web-core"]
        spec = dataclasses.replace(
            profile.template, url=url, versions=profiles.VersionRange(*versions)
        )
        replaced = dataclasses.replace(profile, template=spec)
        monkeypatch.setitem(profiles.PROFILES, "web-core", replaced)
        return replaced

    return apply


@pytest.fixture()
def https_origin(monkeypatch: pytest.MonkeyPatch):
    """Serve the https-style origin HTTPS_ORIGIN from a local bare repo via git's insteadOf.

    Everything that runs git (devkit, Copier in-process, and a `copier update` subprocess) is
    rewritten, so the recorded origin is a real-looking portable URL while no network is
    touched. Copier runs git through plumbum, which snapshots os.environ at import time, so the
    variables are also applied through plumbum's own environment.
    """
    from plumbum import local

    stack = contextlib.ExitStack()

    def serve(remote: Path) -> str:
        values = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"url.{remote}.insteadOf",
            "GIT_CONFIG_VALUE_0": HTTPS_ORIGIN,
        }
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        stack.enter_context(local.env(**values))
        return HTTPS_ORIGIN

    yield serve
    stack.close()


@pytest.fixture()
def point_layers_at(monkeypatch: pytest.MonkeyPatch):
    """Point the web template (all three profiles) and the native template at local origins and ranges."""
    from devkit import layers, upgrade

    def apply(web_url: str, native_url: str, web_versions=((0, 1, 0), (0, 8, 0)), native_versions=((0, 1, 0), (0, 2, 0))):
        web = dataclasses.replace(profiles.PROFILES["web-core"].template, url=web_url, versions=profiles.VersionRange(*web_versions))
        native = dataclasses.replace(profiles.NATIVE_TEMPLATE, url=native_url, versions=profiles.VersionRange(*native_versions))
        for name in ("web-core", "full-stack", "native-ios"):
            profile = profiles.PROFILES[name]
            monkeypatch.setitem(
                profiles.PROFILES, name, dataclasses.replace(profile, template=web, native=native if profile.native else None)
            )
        for module in (profiles, upgrade, layers):
            monkeypatch.setattr(module, "NATIVE_TEMPLATE", native)
        monkeypatch.setattr(upgrade, "NATIVE_ANSWERS_FILE", native.answers_file)
        return web, native

    return apply
