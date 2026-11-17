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
FLAGS_WITH_ZOD = "cache_components={{ cache_components | lower }}\nzod={{ zod | lower }}\n"
FLAGS_WITHOUT_ZOD = "cache_components={{ cache_components | lower }}\n"


def make_versioned_template(destination: Path) -> Path:
    """A mini template whose releases mirror the real one: v0.1.x has no `zod` question, v0.2.x does.

    Releases: v0.1.0, v0.1.1, v0.2.0, v0.2.1. Each writes its version into version.txt.
    """
    full = (MINI_TEMPLATE / "copier.yml").read_text()
    assert ZOD_QUESTION in full
    destination.mkdir(parents=True)
    shutil.copytree(MINI_TEMPLATE / "template", destination / "template")

    def write(copier_yml: str, flags: str) -> None:
        (destination / "copier.yml").write_text(copier_yml)
        (destination / "template" / "flags.txt.jinja").write_text(flags)

    write(full.replace(ZOD_QUESTION, ""), FLAGS_WITHOUT_ZOD)
    run_git(destination, "init", "-q", "-b", "main")
    run_git(destination, "add", "-A")
    run_git(destination, "commit", "-q", "-m", "initial")
    release(destination, "v0.1.0")
    release(destination, "v0.1.1")
    write(full, FLAGS_WITH_ZOD)
    release(destination, "v0.2.0")
    release(destination, "v0.2.1")
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
