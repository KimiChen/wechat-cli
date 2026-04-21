#!/usr/bin/env python3
"""Validate GitHub Release tags against Python package metadata."""

import argparse
import ast
import os
import re
import sys
from pathlib import Path

import tomllib


ROOT = Path(__file__).resolve().parents[1]
TAG_RE = re.compile(r"^v(?P<version>[0-9A-Za-z][0-9A-Za-z.!_+-]*)$")


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Validate a GitHub Release tag against the Python package version.",
    )
    parser.add_argument(
        "tag",
        nargs="?",
        help="Release tag to validate, for example v0.2.5. Defaults to GITHUB_REF_NAME.",
    )
    parser.add_argument(
        "--print-expected-tag",
        action="store_true",
        help="Print the expected release tag and exit.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root to validate. Defaults to the current repository.",
    )
    args = parser.parse_args()

    if args.print_expected_tag and args.tag:
        parser.error("--print-expected-tag does not accept a tag argument")

    return args


def _version_paths(root):
    root = Path(root).resolve()
    return root / "pyproject.toml", root / "wechat_cli" / "__init__.py"


def _read_pyproject_version(path):
    with Path(path).open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def _read_package_version(path):
    source = Path(path).read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(path))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__version__":
                value = ast.literal_eval(node.value)
                if isinstance(value, str):
                    return value
                break
    raise RuntimeError(f"Unable to read __version__ from {path}")


def read_versions(root):
    pyproject_path, package_init_path = _version_paths(root)
    return {
        "python_project_version": _read_pyproject_version(pyproject_path),
        "python_cli_version": _read_package_version(package_init_path),
    }


def expected_release_tag(root):
    versions = read_versions(root)
    project_version = versions["python_project_version"]
    cli_version = versions["python_cli_version"]
    if cli_version != project_version:
        raise RuntimeError(
            "Current versions are misaligned. "
            f"pyproject.toml={project_version}, wechat_cli/__init__.py={cli_version}"
        )
    return f"v{project_version}"


def validate_release_tag(tag, *, root=ROOT):
    versions = read_versions(root)
    project_version = versions["python_project_version"]
    cli_version = versions["python_cli_version"]
    errors = []

    if cli_version != project_version:
        errors.append(
            "Current versions are misaligned. "
            f"pyproject.toml={project_version}, wechat_cli/__init__.py={cli_version}"
        )

    match = TAG_RE.fullmatch(tag)
    if not match:
        errors.append(f"Release tag must match the format v<version>: {tag!r}")
        return errors

    tag_version = match.group("version")
    if tag_version != project_version:
        errors.append(
            "Release tag does not match pyproject.toml version: "
            f"{tag_version} != {project_version}"
        )

    return errors


def assert_release_tag(tag, *, root=ROOT):
    errors = validate_release_tag(tag, root=root)
    if errors:
        joined = "\n".join(f"- {error}" for error in errors)
        raise RuntimeError(f"Release tag check failed:\n{joined}")


def main():
    args = _parse_args()
    root = Path(args.root).resolve()

    if args.print_expected_tag:
        print(expected_release_tag(root))
        return

    tag = args.tag or os.environ.get("GITHUB_REF_NAME")
    if not tag:
        raise RuntimeError("No release tag provided. Pass a tag argument or set GITHUB_REF_NAME.")

    assert_release_tag(tag, root=root)
    print(f"[+] Release tag matches Python package version: {tag}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"[-] {exc}", file=sys.stderr)
        sys.exit(1)
