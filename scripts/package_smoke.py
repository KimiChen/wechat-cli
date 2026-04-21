#!/usr/bin/env python3
"""Run lightweight packaging smoke checks for Python and npm artifacts."""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from check_release_metadata import assert_release_metadata
from check_platform_packages import (
    any_platform_binaries_present,
    assert_packed_platform_artifact,
    assert_platform_packages,
)

ROOT = Path(__file__).resolve().parents[1]
NPM_ROOT = ROOT / "npm"


def _run(cmd, *, cwd):
    print(f"[+] Running in {cwd}: {' '.join(str(part) for part in cmd)}")
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if stdout:
        print(stdout)
    if stderr:
        print(stderr)
    return stdout


def _require_tool(tool_name):
    path = shutil.which(tool_name)
    if path:
        return path
    raise RuntimeError(f"Required tool not found on PATH: {tool_name}")


def _package_dirs():
    package_dirs = [NPM_ROOT / "wechat-cli"]
    package_dirs.extend(
        sorted(
            path
            for path in (NPM_ROOT / "platforms").iterdir()
            if path.is_dir() and (path / "package.json").exists()
        )
    )
    return package_dirs


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Run packaging smoke checks for Python and npm artifacts.",
    )
    parser.add_argument(
        "--require-platform-binaries",
        action="store_true",
        help="Require npm/platforms/* packages to contain real bin/wechat-cli(.exe) files.",
    )
    return parser.parse_args()


def _should_require_platform_binaries(args):
    if args.require_platform_binaries:
        print("[+] Strict platform package validation enabled by CLI flag")
        return True

    if any_platform_binaries_present(ROOT):
        print("[+] Detected built platform binaries; enabling strict platform package validation")
        return True

    print(
        "[+] No built platform binaries detected; platform packages will be validated in manifest-only mode"
    )
    return False


def build_python_package(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    _run(
        [
            sys.executable,
            "-m",
            "build",
            "--sdist",
            "--wheel",
            "--outdir",
            str(output_dir),
        ],
        cwd=ROOT,
    )
    artifacts = sorted(path.name for path in output_dir.iterdir() if path.is_file())
    if not artifacts:
        raise RuntimeError("Python packaging smoke failed: no artifacts were produced")
    print(f"[+] Python artifacts: {', '.join(artifacts)}")


def pack_npm_packages(output_dir, npm_executable, require_platform_binaries=False):
    output_dir.mkdir(parents=True, exist_ok=True)
    packed_files = []
    for package_dir in _package_dirs():
        stdout = _run([npm_executable, "pack", str(package_dir.resolve())], cwd=output_dir)
        package_name = stdout.splitlines()[-1].strip() if stdout else ""
        if not package_name:
            raise RuntimeError(f"npm pack did not report an artifact for {package_dir}")
        artifact_path = output_dir / package_name
        if not artifact_path.exists():
            raise RuntimeError(f"Expected npm artifact missing: {artifact_path}")
        if require_platform_binaries and package_dir.parent == (NPM_ROOT / "platforms"):
            assert_packed_platform_artifact(artifact_path, package_dir.name)
        packed_files.append(package_name)
    print(f"[+] npm artifacts: {', '.join(packed_files)}")


def main():
    args = _parse_args()
    npm_executable = _require_tool("npm")
    require_platform_binaries = _should_require_platform_binaries(args)
    assert_release_metadata()
    print("[+] Release metadata is aligned")
    assert_platform_packages(ROOT, require_binaries=require_platform_binaries)
    print("[+] Platform package manifests are aligned")

    with tempfile.TemporaryDirectory(prefix="wechat-cli-package-smoke-") as tmpdir:
        tmp_root = Path(tmpdir)
        build_python_package(tmp_root / "python")
        pack_npm_packages(
            tmp_root / "npm",
            npm_executable,
            require_platform_binaries=require_platform_binaries,
        )

    print("[+] Packaging smoke checks passed")


if __name__ == "__main__":
    main()
