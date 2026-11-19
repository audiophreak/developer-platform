#!/usr/bin/env python3
"""Capture (or verify) a snapshot of a template release's contract with devkit.

    uv run python tools/capture_contract.py --template ../web-core-template --ref v0.1.0 --write
    uv run python tools/capture_contract.py --template ../web-core-template --ref HEAD --version 0.2.0 --write
    uv run python tools/capture_contract.py --template ../web-core-template --ref v0.2.0 --check
    uv run python tools/capture_contract.py --kind native-ios --template ../native-ios-template --ref v0.1.0 --write

A snapshot (`tests/contracts/web-core/<version>.json`) records what devkit depends on: each question
of copier.yml with its type, default and choices, and the Node.js major the release pins. Offline
tests compare the profile registry with every snapshot, so CI can verify compatibility with each
supported release without credentials or network access. `--check` compares a snapshot with the real
template (a release tag, or the working tree for an unreleased version): it is the release gate,
run where the template is checked out, and the only part that needs it.

Reading a release uses `git show REF:path`, so a tag is captured as it was released.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_ROOT = ROOT / "tests" / "contracts"
CONTRACTS = CONTRACTS_ROOT / "web-core"  # the default kind; `--kind native-ios` uses its own directory
IGNORED_WHEN_COMPARING = {"captured_from"}


class CaptureError(RuntimeError):
    pass


def read_file(template: Path, ref: str, relative: str) -> str:
    """A file as it is at `ref`; HEAD means the working tree (what Copier renders in development)."""
    if ref == "HEAD":
        try:
            return (template / relative).read_text(encoding="utf-8")
        except OSError as exc:
            raise CaptureError(f"cannot read {relative} from the working tree: {exc}") from exc
    result = subprocess.run(
        ["git", "-C", str(template), "show", f"{ref}:{relative}"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise CaptureError(f"cannot read {relative} at {ref}: {result.stderr.strip()}")
    return result.stdout


def capture(template: Path, ref: str, version: str, kind: str = "web-core") -> dict:
    config = yaml.safe_load(read_file(template, ref, "copier.yml")) or {}
    questions: dict[str, dict] = {}
    for name, body in config.items():
        if name.startswith("_") or not isinstance(body, dict):
            continue
        entry: dict = {"type": body.get("type", "str")}
        for key in ("default", "choices"):
            if key in body:
                entry[key] = body[key]
        if body.get("when") is False:
            entry["computed"] = True
        questions[name] = entry
    snapshot = {
        "template": "web-core-template" if kind == "web-core" else "native-ios-template",
        "release": f"v{version}",
        "captured_from": f"tag {ref}" if ref != "HEAD" else "working tree (unreleased; re-capture from the tag)",
        "questions": questions,
    }
    if kind == "native-ios":
        snapshot["answers_file"] = str(config.get("_answers_file", ".copier-answers.yml"))  # a layer must not share Copier's default
    if kind == "web-core":
        nvmrc = read_file(template, ref, "template/.nvmrc").strip()
        match = re.match(r"v?(\d+)", nvmrc)
        if not match:
            raise CaptureError(f"template/.nvmrc is not a version: {nvmrc!r}")
        snapshot["node_major"] = int(match.group(1))
    return snapshot


def render(snapshot: dict) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True) + "\n"


def comparable(snapshot: dict) -> dict:
    return {k: v for k, v in snapshot.items() if k not in IGNORED_WHEN_COMPARING}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kind", choices=["web-core", "native-ios"], default="web-core", help="which template (default: web-core)")
    parser.add_argument("--template", type=Path, required=True, help="path to the template checkout")
    parser.add_argument("--ref", required=True, help="a release tag (v0.1.0) or HEAD for the working tree")
    parser.add_argument("--version", help="X.Y.Z; required with HEAD, otherwise taken from the tag")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write tests/contracts/<kind>/<version>.json")
    mode.add_argument("--check", action="store_true", help="exit 1 if the committed snapshot differs")
    args = parser.parse_args(argv)

    tag = re.fullmatch(r"v(\d+\.\d+\.\d+)", args.ref)
    version = args.version or (tag.group(1) if tag else None)
    if version is None:
        print("--version is required unless --ref is a release tag", file=sys.stderr)
        return 2
    if tag and args.version and args.version != tag.group(1):
        print(f"--version {args.version} does not match tag {args.ref}", file=sys.stderr)
        return 2
    try:
        snapshot = capture(args.template.expanduser().resolve(), args.ref, version, args.kind)
    except CaptureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    directory = CONTRACTS_ROOT / args.kind
    target = directory / f"{version}.json"
    if args.write:
        directory.mkdir(parents=True, exist_ok=True)
        target.write_text(render(snapshot), encoding="utf-8")
        print(f"wrote {target.relative_to(ROOT)} (from {snapshot['captured_from']})")
        return 0
    if not target.is_file():
        print(f"missing snapshot {target.relative_to(ROOT)}", file=sys.stderr)
        return 1
    committed = json.loads(target.read_text(encoding="utf-8"))
    if comparable(committed) != comparable(snapshot):
        print(f"DRIFT: {target.relative_to(ROOT)} differs from the template at {args.ref}; re-capture it", file=sys.stderr)
        return 1
    print(f"{target.relative_to(ROOT)} matches the template at {args.ref}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
