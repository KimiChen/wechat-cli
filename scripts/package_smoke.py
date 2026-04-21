#!/usr/bin/env python3
"""Run lightweight packaging smoke checks for Python artifacts."""

import subprocess
import sys
import tempfile
from pathlib import Path

from check_release_metadata import assert_release_metadata


ROOT = Path(__file__).resolve().parents[1]


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


def main():
    assert_release_metadata()
    print("[+] Python release metadata is aligned")

    with tempfile.TemporaryDirectory(prefix="wechat-cli-package-smoke-") as tmpdir:
        tmp_root = Path(tmpdir)
        build_python_package(tmp_root / "python")

    print("[+] Python packaging smoke checks passed")


if __name__ == "__main__":
    main()
