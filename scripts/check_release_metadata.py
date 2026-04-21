#!/usr/bin/env python3
"""Validate release metadata stays aligned across Python and npm packages."""

import json
from pathlib import Path
import tomllib

from wechat_cli import __version__


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
NPM_ROOT_PACKAGE = ROOT / "npm" / "wechat-cli" / "package.json"
NPM_PLATFORM_DIR = ROOT / "npm" / "platforms"
NPM_PACKAGE_METADATA = ROOT / "npm" / "wechat-cli" / "package-metadata.json"


def _read_json(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _read_pyproject():
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)


def collect_release_metadata():
    pyproject = _read_pyproject()
    npm_root = _read_json(NPM_ROOT_PACKAGE)
    npm_metadata = _read_json(NPM_PACKAGE_METADATA)

    platform_packages = {}
    for package_path in sorted(NPM_PLATFORM_DIR.glob("*/package.json")):
        package_json = _read_json(package_path)
        platform_packages[package_path.parent.name] = package_json

    return {
        "python_project_version": pyproject["project"]["version"],
        "python_cli_version": __version__,
        "npm_root_package": npm_root,
        "npm_package_metadata": npm_metadata,
        "npm_platform_packages": platform_packages,
    }


def validate_release_metadata():
    metadata = collect_release_metadata()
    errors = []

    expected_version = metadata["python_project_version"]
    if metadata["python_cli_version"] != expected_version:
        errors.append(
            "Python CLI version mismatch: "
            f"{metadata['python_cli_version']} != {expected_version}"
        )

    npm_root = metadata["npm_root_package"]
    if npm_root["version"] != expected_version:
        errors.append(
            "npm wrapper version mismatch: "
            f"{npm_root['version']} != {expected_version}"
        )

    npm_package_metadata = metadata["npm_package_metadata"]
    if npm_package_metadata["root_package"] != npm_root["name"]:
        errors.append(
            "npm root package name mismatch: "
            f"{npm_package_metadata['root_package']} != {npm_root['name']}"
        )

    optional_dependencies = npm_root.get("optionalDependencies", {})
    expected_platform_packages = npm_package_metadata["platform_packages"]
    actual_optional_dependency_names = set(optional_dependencies.keys())
    expected_optional_dependency_names = set(expected_platform_packages.values())
    if actual_optional_dependency_names != expected_optional_dependency_names:
        errors.append(
            "npm optionalDependencies do not match shared platform package metadata: "
            f"{sorted(actual_optional_dependency_names)} != {sorted(expected_optional_dependency_names)}"
        )

    for package_name, version in optional_dependencies.items():
        if version != expected_version:
            errors.append(
                "npm optional dependency version mismatch: "
                f"{package_name} -> {version} != {expected_version}"
            )

    for platform_key, package_json in metadata["npm_platform_packages"].items():
        expected_name = expected_platform_packages.get(platform_key)
        if not expected_name:
            errors.append(f"Missing shared metadata entry for platform {platform_key}")
            continue
        if package_json["name"] != expected_name:
            errors.append(
                "Platform package name mismatch: "
                f"{platform_key} -> {package_json['name']} != {expected_name}"
            )
        if package_json["version"] != expected_version:
            errors.append(
                "Platform package version mismatch: "
                f"{platform_key} -> {package_json['version']} != {expected_version}"
            )

    return errors


def assert_release_metadata():
    errors = validate_release_metadata()
    if errors:
        joined = "\n".join(f"- {error}" for error in errors)
        raise RuntimeError(f"Release metadata check failed:\n{joined}")


def main():
    assert_release_metadata()
    print("[+] Release metadata is aligned")


if __name__ == "__main__":
    main()
