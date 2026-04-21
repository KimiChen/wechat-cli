#!/usr/bin/env python3
"""Run Python release validation and packaging smoke."""

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Run Python release validation and package smoke checks.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip unittest discovery.",
    )
    parser.add_argument(
        "--skip-compileall",
        action="store_true",
        help="Skip compileall syntax checks.",
    )
    parser.add_argument(
        "--skip-package-smoke",
        action="store_true",
        help="Skip scripts/package_smoke.py.",
    )
    parser.add_argument(
        "--tag",
        help="Optional release tag to validate before running checks, for example v0.2.5.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned commands without executing them.",
    )
    return parser.parse_args()


def _format_cmd(cmd):
    return " ".join(str(part) for part in cmd)


def _build_command_plan(args):
    commands = []
    if args.tag:
        commands.append([sys.executable, "scripts/check_release_tag.py", args.tag])
    if not args.skip_tests:
        commands.append([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    if not args.skip_compileall:
        commands.append([sys.executable, "-m", "compileall", "wechat_cli", "tests", "scripts"])
    if not args.skip_package_smoke:
        commands.append([sys.executable, "scripts/package_smoke.py"])
    return commands


def _run_commands(commands, dry_run=False):
    if not commands:
        print("[+] No commands selected")
        return

    for index, cmd in enumerate(commands, start=1):
        print(f"[+] Step {index}/{len(commands)}: {_format_cmd(cmd)}")
        if dry_run:
            continue
        subprocess.run(cmd, cwd=ROOT, check=True)


def main():
    args = _parse_args()
    print("[+] Release prep uses the Python-only packaging workflow")
    commands = _build_command_plan(args)
    try:
        _run_commands(commands, dry_run=args.dry_run)
    except subprocess.CalledProcessError as e:
        print(f"[-] Release prep failed while running: {_format_cmd(e.cmd)}", file=sys.stderr)
        sys.exit(e.returncode or 1)
    if args.dry_run:
        print("[+] Dry run completed")
    else:
        print("[+] Release prep completed")


if __name__ == "__main__":
    main()
