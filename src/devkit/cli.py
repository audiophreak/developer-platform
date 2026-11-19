"""devkit command line: `doctor`, `new`, `upgrade`, `status` and `native add`.

Exit codes: 0 success; 1 a check failed or the operation failed; 2 rejected input or usage;
3 an upgrade finished but left merge conflicts for you to resolve (nothing is discarded).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, doctor
from .errors import DevkitError, OperationError as OperationError_
from .generate import NewRequest, generate_project
from .gitutil import redact
from .paths import find_platform_root
from .profiles import DEFAULT_PROFILE, PROFILES
from .sources import format_tag
from .layers import AddNativeRequest, add_native_layer, layer_statuses, pair_problem
from .upgrade import UpgradePlan, UpgradeRequest, upgrade_project

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
        help=(
            f"technology profile (default: {DEFAULT_PROFILE}). full-stack = web + Zod + REST API + auth, with the "
            "database provider chosen by --set database=postgres|supabase; native-ios = full-stack + a native SwiftUI iOS app"
        ),
    )
    new.add_argument(
        "--set",
        dest="options",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="set a template option such as zod=true, database=postgres, auth=true or cache_components=false (repeatable)",
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
        "--native-template",
        default=None,
        metavar="PATH_OR_URL",
        help="profile native-ios, development: render a local native-ios-template checkout instead of the published one",
    )
    new.add_argument("--native-template-ref", default=None, metavar="REF", help="profile native-ios: the native template release tag (vX.Y.Z)")
    new.add_argument(
        "--native-set",
        dest="native_options",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="profile native-ios: app_display_name, bundle_identifier, debug_api_port or release_api_host (repeatable)",
    )
    new.add_argument(
        "--dry-run", action="store_true", help="show what would be created; write nothing"
    )

    upgrade = commands.add_parser(
        "upgrade",
        help="upgrade an existing project to a newer template release",
        description=(
            "Upgrade PROJECT to the newest template release this devkit supports. The project must be a "
            "committed git repository with a clean working tree. Your feature selections are kept; your "
            "own changes are merged, never discarded, and conflicts are reported."
        ),
    )
    upgrade.add_argument("project", type=Path, help="the project directory (the git repository root)")
    upgrade.add_argument("--to", default=None, metavar="vX.Y.Z", help="upgrade to this release instead of the newest supported one")
    upgrade.add_argument(
        "--set",
        dest="options",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="change an option or feature while upgrading, e.g. --set zod=true (repeatable); an established database provider and an established auth selection cannot be changed",
    )
    upgrade.add_argument("--profile", default=DEFAULT_PROFILE, choices=sorted(PROFILES), help="profile whose supported range applies")
    upgrade.add_argument(
        "--layer",
        default="auto",
        choices=["auto", "web", "native"],
        help="a native-ios project has two layers with their own releases; upgrade one at a time (required there)",
    )
    upgrade.add_argument("--dry-run", action="store_true", help="show the plan and run Copier's preview; change nothing")

    status = commands.add_parser(
        "status",
        help="show the template layers of a project and what is newer (read-only)",
        description="Show each template layer of PROJECT (web, and native iOS if present), its release and the newest supported one.",
    )
    status.add_argument("project", type=Path, help="the project directory")

    native = commands.add_parser("native", help="the native iOS layer of an existing project")
    native_commands = native.add_subparsers(dest="native_command", required=True, metavar="ACTION")
    add = native_commands.add_parser(
        "add",
        help="add the native iOS layer to a full-stack project",
        description=(
            "Apply the native iOS template to PROJECT (a committed, clean git repository whose web part is full-stack "
            "with native_client enabled). Only adds ios/ and .copier-answers.ios.yml; changes none of your files."
        ),
    )
    add.add_argument("project", type=Path, help="the project directory (the git repository root)")
    add.add_argument("--native-template", default=None, metavar="PATH_OR_URL", help="development: a local native-ios-template checkout")
    add.add_argument("--native-template-ref", default=None, metavar="REF", help="the native template release tag (vX.Y.Z)")
    add.add_argument("--native-set", dest="native_options", action="append", default=[], metavar="NAME=VALUE", help="app_display_name, bundle_identifier, debug_api_port or release_api_host (repeatable)")
    add.add_argument("--dry-run", action="store_true", help="show what would be added; write nothing")
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
        native_template=args.native_template,
        native_template_ref=args.native_template_ref,
        native_options=tuple(args.native_options),
    )
    prefix = "[dry run] " if request.dry_run else ""

    def announce(template) -> None:
        where = f"{redact(template.location)} @ {template.ref}" if template.ref else template.location
        print(f"{prefix}Profile {request.profile!r}, {template.mode} template {where}", flush=True)
        if request.options:
            print(f"{prefix}Options: {' '.join(request.options)}", flush=True)
        for note in template.warnings:
            print(f"warning: {note}", file=sys.stderr, flush=True)

    result = generate_project(request, on_resolved=announce)
    if result.dry_run:
        print(f"\nDry run complete. Nothing was written. Would create: {result.destination}")
        return EXIT_OK
    steps = (
        f"  cd {result.destination}\n"
        "  git init && git add -A && git commit -m 'chore: initial commit'\n"
        "  npm ci\n"
        "  npm run check"
    )
    if result.native is not None:
        where = f"{redact(result.native.location)} @ {result.native.ref}" if result.native.ref else result.native.location
        print(f"Native iOS layer: {where}")
        steps += (
            "\n  npm run db:init && npm run db:up && npm run db:migrate   # then `npm run test:db`\n"
            "  open ios/App.xcodeproj    # Xcode 26+; or: sh ios/scripts/test.sh\n"
            "  node ios/scripts/e2e.mjs  # the real end-to-end scenario on the simulator\n"
            "Read AGENTS.md (web) and ios/AGENTS.md (iOS). The two layers upgrade separately: `devkit status`."
        )
    print(f"\nCreated {result.destination}\n\nNext steps:\n{steps}")
    return EXIT_OK


def _print_plan(plan: UpgradePlan, dry_run: bool) -> None:
    prefix = "[dry run] " if dry_run else ""
    print(f"{prefix}Project: {plan.project}")
    print(f"{prefix}Template: {redact(plan.source)}")
    if plan.target is None:
        print(f"{prefix}Installed {format_tag(plan.installed)}: already up to date (nothing newer is supported).")
    else:
        print(f"{prefix}Upgrading {format_tag(plan.installed)} -> {format_tag(plan.target)}", flush=True)
        if plan.preserved:
            print(f"{prefix}Keeping your answers: " + " ".join(f"{k}={v}" for k, v in sorted(plan.preserved.items())))
        if plan.options:
            print(f"{prefix}Changing: " + " ".join(f"{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in plan.options.items()))
        if plan.crosses_minor:
            print(f"{prefix}Note: this crosses a minor version, which may contain breaking changes; read the template CHANGELOG.")
    for note in plan.warnings:
        print(f"warning: {note}", file=sys.stderr, flush=True)


def _cmd_upgrade(args: argparse.Namespace) -> int:
    request = UpgradeRequest(
        project=args.project, to=args.to, options=tuple(args.options), profile=args.profile, dry_run=args.dry_run,
        layer=args.layer,
    )
    result = upgrade_project(request, on_plan=lambda plan: _print_plan(plan, request.dry_run))
    if result.plan.target is None:
        return EXIT_OK
    if result.dry_run:
        print("\nDry run complete. Nothing was changed.")
        return EXIT_OK
    layer = result.plan.layer
    check = "npm ci                   # the lockfile matches your feature selection\n  npm run check" if layer == "web" else "sh ios/scripts/check-contract.sh && sh ios/scripts/test.sh"
    print(
        f"\nUpgraded the {layer} layer to {format_tag(result.plan.target)}.\n\nNext steps:\n"
        "  git diff                 # review what changed\n"
        f"  {check}\n"
        f"  git add -A && git commit -m 'chore: update {layer} template to {format_tag(result.plan.target)}'"
    )
    for item in result.plan.pending:
        print(f"NOT fully upgraded: {item}. Commit this first, then `devkit upgrade {result.plan.project} --layer <other>`.", file=sys.stderr)
    return EXIT_OK


def _cmd_status(args: argparse.Namespace) -> int:
    statuses = layer_statuses(args.project)
    if not statuses:
        raise OperationError_(f"{args.project} has no Copier answers file: it was not generated by devkit's templates.")
    for item in statuses:
        installed = format_tag(item.installed) if item.installed else "unknown"
        state = "up to date" if not item.pending else f"newer available: {format_tag(item.newest)}"
        suffix = f"  ({item.note})" if item.note else ""
        print(f"{item.layer:<7} {installed:<9} {state}{suffix}")
    problem = pair_problem(statuses)
    if problem:
        print(f"warning: {problem}", file=sys.stderr)
        return 1
    if any(item.pending for item in statuses):
        print("\nThe project is NOT fully upgraded. Upgrade one layer at a time: devkit upgrade PROJECT --layer web|native", file=sys.stderr)
    return EXIT_OK


def _cmd_native_add(args: argparse.Namespace) -> int:
    request = AddNativeRequest(
        project=args.project, native_template=args.native_template, native_template_ref=args.native_template_ref,
        native_options=tuple(args.native_options), dry_run=args.dry_run,
    )
    native = add_native_layer(request)
    if request.dry_run:
        print("Dry run complete. Nothing was written.")
        return EXIT_OK
    where = f"{redact(native.location)} @ {native.ref}" if native.ref else native.location
    print(
        f"Added the native iOS layer from {where}.\n\nNext steps:\n"
        "  git status               # only ios/ and .copier-answers.ios.yml are new\n"
        "  sh ios/scripts/check-contract.sh && sh ios/scripts/test.sh\n"
        "  git add -A && git commit -m 'feat: add the native iOS layer'"
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            return _cmd_doctor()
        if args.command == "upgrade":
            return _cmd_upgrade(args)
        if args.command == "status":
            return _cmd_status(args)
        if args.command == "native":
            return _cmd_native_add(args)
        return _cmd_new(args)
    except DevkitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
