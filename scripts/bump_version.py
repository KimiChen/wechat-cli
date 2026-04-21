#!/usr/bin/env python3
"""Synchronize Python package version metadata."""

import argparse
import re
import sys
from pathlib import Path

import tomllib


ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.!_+-]*$")
PYPROJECT_VERSION_RE = re.compile(r'(?m)^(version\s*=\s*")([^"]+)(")')
PACKAGE_INIT_VERSION_RE = re.compile(r'(?m)^(__version__\s*=\s*")([^"]+)(")')


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Update pyproject.toml and wechat_cli/__init__.py to the same version.",
    )
    parser.add_argument(
        "version",
        nargs="?",
        help="New version string, for example 0.2.5.",
    )
    parser.add_argument(
        "--print-current",
        action="store_true",
        help="Print the current synchronized version and exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the planned changes without writing files.",
    )
    parser.add_argument(
        "--allow-misaligned",
        action="store_true",
        help="Update files even if the current versions do not match.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root to update. Defaults to the current repository.",
    )
    args = parser.parse_args()

    if args.print_current and args.version:
        parser.error("--print-current does not accept a version argument")
    if not args.print_current and not args.version:
        parser.error("a new version is required unless --print-current is used")
    if args.version and not VERSION_RE.fullmatch(args.version):
        parser.error(f"invalid version string: {args.version!r}")

    return args


def _version_paths(root):
    root = Path(root).resolve()
    return root / "pyproject.toml", root / "wechat_cli" / "__init__.py"


def _read_pyproject_version(path):
    with Path(path).open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def _read_package_version(path):
    match = PACKAGE_INIT_VERSION_RE.search(Path(path).read_text(encoding="utf-8"))
    if not match:
        raise RuntimeError(f"Unable to find __version__ in {path}")
    return match.group(2)


def read_versions(root):
    pyproject_path, package_init_path = _version_paths(root)
    return {
        "pyproject.toml": _read_pyproject_version(pyproject_path),
        "wechat_cli/__init__.py": _read_package_version(package_init_path),
    }


def _replace_single(text, pattern, new_version, *, label, path):
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {label} assignment in {path}, found {len(matches)}")
    match = matches[0]
    return f"{text[:match.start(2)]}{new_version}{text[match.end(2):]}"


def _write_versions(root, new_version, dry_run=False):
    pyproject_path, package_init_path = _version_paths(root)
    pyproject_text = pyproject_path.read_text(encoding="utf-8")
    package_init_text = package_init_path.read_text(encoding="utf-8")

    next_pyproject = _replace_single(
        pyproject_text,
        PYPROJECT_VERSION_RE,
        new_version,
        label="pyproject version",
        path=pyproject_path,
    )
    next_package_init = _replace_single(
        package_init_text,
        PACKAGE_INIT_VERSION_RE,
        new_version,
        label="package __version__",
        path=package_init_path,
    )

    if dry_run:
        print(f"[+] Would update {pyproject_path} -> {new_version}")
        print(f"[+] Would update {package_init_path} -> {new_version}")
        return

    pyproject_path.write_text(next_pyproject, encoding="utf-8")
    package_init_path.write_text(next_package_init, encoding="utf-8")
    print(f"[+] Updated {pyproject_path} -> {new_version}")
    print(f"[+] Updated {package_init_path} -> {new_version}")


def main():
    args = _parse_args()
    versions = read_versions(args.root)
    pyproject_version = versions["pyproject.toml"]
    package_version = versions["wechat_cli/__init__.py"]

    if args.print_current:
        if pyproject_version == package_version:
            print(pyproject_version)
            return
        print(
            "Current versions are misaligned: "
            f"pyproject.toml={pyproject_version}, "
            f"wechat_cli/__init__.py={package_version}",
            file=sys.stderr,
        )
        sys.exit(1)

    if pyproject_version != package_version and not args.allow_misaligned:
        raise RuntimeError(
            "Current versions are misaligned. "
            "Fix them first or rerun with --allow-misaligned."
        )

    current_version = pyproject_version if pyproject_version == package_version else "misaligned"
    if pyproject_version == package_version and args.version == pyproject_version:
        print(f"[+] Version already set to {args.version}")
        return

    print(f"[+] Version change: {current_version} -> {args.version}")
    _write_versions(args.root, args.version, dry_run=args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"[-] {exc}", file=sys.stderr)
        sys.exit(1)
