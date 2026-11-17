"""devkit command line: `doctor` and `new`.

Exit codes: 0 success; 1 a check failed or generation failed; 2 rejected input or usage.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, doctor
from .errors import DevkitError
from .generate import NewRequest, generate_project
from .gitutil import redact
from .paths import find_platform_root
from .profiles import DEFAULT_PROFILE, PROFILES

EXIT_OK = 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="devkit",
        description="Generate and validate new applications from versioned templates.",
    )
    parser.add_argument("--version", action="version", version=f"devkit {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    commands.add_parser(
        "doctor",
        help="check workstation prerequisites (read-only)",
        description="Check workstation prerequisites. Read-only: installs and changes nothing.",
    )

    new = commands.add_parser(
        "new",
        help="create a new application",
        description=(
            "Create a new application in OUTPUT_DIR/NAME from the profile's template, using the "
            "newest published release this devkit supports. Never overwrites anything."
        ),
    )
    new.add_argument("name", help="application name (the template validates the exact format)")
    new.add_argument("--description", default=None, help="one-line description")
    new.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="existing directory to create the app in (default: current directory)",
    )
    new.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        choices=sorted(PROFILES),
        help=f"technology profile (default: {DEFAULT_PROFILE}; others are reserved)",
    )
    new.add_argument(
        "--set",
        dest="options",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="set a template option, e.g. --set cache_components=false (repeatable)",
    )
    new.add_argument(
        "--template",
        default=None,
        metavar="PATH_OR_URL",
        help=(
            "development: render a local template checkout as it is on disk; or use another "
            "template origin URL. Default: the profile's published template"
        ),
    )
    new.add_argument(
        "--template-ref",
        default=None,
        metavar="REF",
        help=(
            "render this template release tag (vX.Y.Z) instead of the newest supported one; "
            "with a local --template, any git ref"
        ),
    )
    new.add_argument(
        "--dry-run", action="store_true", help="show what would be created; write nothing"
    )
    return parser


def _cmd_doctor() -> int:
    checks = doctor.run_checks(find_platform_root())
    print(doctor.render(checks))
    return doctor.exit_code(checks)


def _cmd_new(args: argparse.Namespace) -> int:
    request = NewRequest(
        name=args.name,
        description=args.description,
        output_dir=args.output_dir if args.output_dir is not None else Path.cwd(),
        profile=args.profile,
        dry_run=args.dry_run,
        template=args.template,
        template_ref=args.template_ref,
        options=tuple(args.options),
    )
    prefix = "[dry run] " if request.dry_run else ""

    def announce(template) -> None:
        where = f"{redact(template.location)} @ {template.ref}" if template.ref else template.location
        print(f"{prefix}Profile {request.profile!r}, {template.mode} template {where}", flush=True)
        for note in template.warnings:
            print(f"warning: {note}", file=sys.stderr, flush=True)

    result = generate_project(request, on_resolved=announce)
    if result.dry_run:
        print(f"\nDry run complete. Nothing was written. Would create: {result.destination}")
        return EXIT_OK
    print(
        f"\nCreated {result.destination}\n\nNext steps:\n"
        f"  cd {result.destination}\n"
        "  git init && git add -A && git commit -m 'chore: initial commit'\n"
        "  npm ci\n"
        "  npm run check"
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            return _cmd_doctor()
        return _cmd_new(args)
    except DevkitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
