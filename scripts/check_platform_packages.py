#!/usr/bin/env python3
"""Validate npm platform package manifests and built binary contents."""

import argparse
import json
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_json(path):
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def _npm_root(root):
    return Path(root) / "npm"


def _platform_root(root):
    return _npm_root(root) / "platforms"


def _metadata_path(root):
    return _npm_root(root) / "wechat-cli" / "package-metadata.json"


def expected_platform_packages(root=ROOT):
    metadata = _read_json(_metadata_path(root))
    return metadata.get("platform_packages", {})


def expected_binary_name(platform_key):
    os_name = platform_key.split("-", 1)[0]
    return "wechat-cli.exe" if os_name == "win32" else "wechat-cli"


def expected_binary_path(root, platform_key):
    return _platform_root(root) / platform_key / "bin" / expected_binary_name(platform_key)


def any_platform_binaries_present(root=ROOT):
    return any(
        expected_binary_path(root, platform_key).exists()
        for platform_key in expected_platform_packages(root)
    )


def _normalize_files_entry(entry):
    return str(entry).rstrip("/\\")


def validate_platform_packages(root=ROOT, require_binaries=False):
    root = Path(root)
    platform_root = _platform_root(root)
    expected_packages = expected_platform_packages(root)
    errors = []

    if not expected_packages:
        return [f"No platform package metadata found in {_metadata_path(root)}"]

    actual_platform_dirs = set()
    if platform_root.exists():
        actual_platform_dirs = {path.name for path in platform_root.iterdir() if path.is_dir()}

    expected_platform_dirs = set(expected_packages)
    missing_dirs = sorted(expected_platform_dirs - actual_platform_dirs)
    extra_dirs = sorted(actual_platform_dirs - expected_platform_dirs)
    if missing_dirs:
        errors.append(f"Missing platform package directories: {', '.join(missing_dirs)}")
    if extra_dirs:
        errors.append(f"Unexpected platform package directories: {', '.join(extra_dirs)}")

    for platform_key, expected_name in sorted(expected_packages.items()):
        package_json_path = platform_root / platform_key / "package.json"
        if not package_json_path.exists():
            errors.append(f"Missing platform package manifest: {package_json_path}")
            continue

        try:
            package_json = _read_json(package_json_path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"Failed to read {package_json_path}: {exc}")
            continue

        if package_json.get("name") != expected_name:
            errors.append(
                f"Platform package name mismatch for {platform_key}: "
                f"{package_json.get('name')} != {expected_name}"
            )

        os_name, cpu_arch = platform_key.split("-", 1)
        if package_json.get("os") != [os_name]:
            errors.append(
                f"Platform package os mismatch for {platform_key}: "
                f"{package_json.get('os')} != {[os_name]}"
            )
        if package_json.get("cpu") != [cpu_arch]:
            errors.append(
                f"Platform package cpu mismatch for {platform_key}: "
                f"{package_json.get('cpu')} != {[cpu_arch]}"
            )

        files = package_json.get("files") or []
        normalized_files = {_normalize_files_entry(entry) for entry in files if entry}
        if "bin" not in normalized_files:
            errors.append(
                f"Platform package files list must include 'bin/' for {platform_key}: {files}"
            )

        if require_binaries:
            binary_path = expected_binary_path(root, platform_key)
            if not binary_path.is_file():
                errors.append(f"Missing platform binary for {platform_key}: {binary_path}")
            elif binary_path.stat().st_size <= 0:
                errors.append(f"Platform binary is empty for {platform_key}: {binary_path}")

    return errors


def assert_platform_packages(root=ROOT, require_binaries=False):
    errors = validate_platform_packages(root=root, require_binaries=require_binaries)
    if errors:
        joined = "\n".join(f"- {error}" for error in errors)
        raise RuntimeError(f"Platform package validation failed:\n{joined}")


def validate_packed_platform_artifact(artifact_path, platform_key, require_binaries=True):
    artifact_path = Path(artifact_path)
    if not artifact_path.exists():
        return [f"Packed artifact missing: {artifact_path}"]

    try:
        with tarfile.open(artifact_path, "r:gz") as archive:
            members = set(archive.getnames())
    except (OSError, tarfile.TarError) as exc:
        return [f"Failed to inspect packed artifact {artifact_path}: {exc}"]

    errors = []
    if "package/package.json" not in members:
        errors.append(f"Packed artifact is missing package/package.json: {artifact_path}")

    if require_binaries:
        expected_member = f"package/bin/{expected_binary_name(platform_key)}"
        if expected_member not in members:
            errors.append(
                f"Packed artifact is missing {expected_member}: {artifact_path}"
            )

    return errors


def assert_packed_platform_artifact(artifact_path, platform_key, require_binaries=True):
    errors = validate_packed_platform_artifact(
        artifact_path,
        platform_key,
        require_binaries=require_binaries,
    )
    if errors:
        joined = "\n".join(f"- {error}" for error in errors)
        raise RuntimeError(f"Packed platform artifact validation failed:\n{joined}")


def main():
    parser = argparse.ArgumentParser(
        description="Validate npm platform package manifests and optional built binaries.",
    )
    parser.add_argument(
        "--root",
        default=str(ROOT),
        help="Repository root to validate (defaults to current repo root).",
    )
    parser.add_argument(
        "--require-binaries",
        action="store_true",
        help="Require each platform package to contain a built bin/wechat-cli(.exe).",
    )
    args = parser.parse_args()

    assert_platform_packages(root=args.root, require_binaries=args.require_binaries)
    mode = "strict" if args.require_binaries else "manifest-only"
    print(f"[+] Platform packages look good ({mode} mode)")


if __name__ == "__main__":
    main()
