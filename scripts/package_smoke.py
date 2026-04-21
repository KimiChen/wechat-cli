#!/usr/bin/env python3
"""Run lightweight packaging smoke checks for Python artifacts."""

import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

from check_release_metadata import assert_release_metadata


ROOT = Path(__file__).resolve().parents[1]


def _subprocess_env():
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("VIRTUAL_ENV", None)
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    env.setdefault("PYTHONUTF8", "1")
    return env


def _run(cmd, *, cwd):
    print(f"[+] Running in {cwd}: {' '.join(str(part) for part in cmd)}")
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_subprocess_env(),
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if stdout:
        print(stdout)
    if stderr:
        print(stderr)
    return stdout


def collect_python_artifacts(output_dir):
    artifacts = {}
    duplicates = set()

    for path in sorted(Path(output_dir).iterdir()):
        if not path.is_file():
            continue
        if path.name.endswith(".whl"):
            key = "wheel"
        elif path.name.endswith(".tar.gz"):
            key = "sdist"
        else:
            continue

        if key in artifacts:
            duplicates.add(key)
        artifacts[key] = path

    if duplicates:
        raise RuntimeError(
            "Python packaging smoke failed: multiple artifacts found for "
            + ", ".join(sorted(duplicates))
        )

    missing = [key for key in ("sdist", "wheel") if key not in artifacts]
    if missing:
        raise RuntimeError(
            "Python packaging smoke failed: missing expected artifacts: "
            + ", ".join(missing)
        )

    return artifacts


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
    artifacts = collect_python_artifacts(output_dir)
    print(
        "[+] Python artifacts: "
        + ", ".join(str(path.name) for path in artifacts.values())
    )
    return artifacts


def _venv_bin_dir(venv_dir):
    return Path(venv_dir) / ("Scripts" if os.name == "nt" else "bin")


def venv_python_path(venv_dir):
    bin_dir = _venv_bin_dir(venv_dir)
    return bin_dir / ("python.exe" if os.name == "nt" else "python")


def venv_cli_path(venv_dir):
    bin_dir = _venv_bin_dir(venv_dir)
    return bin_dir / ("wechat-cli.exe" if os.name == "nt" else "wechat-cli")


def create_virtualenv(venv_dir):
    print(f"[+] Creating virtual environment: {venv_dir}")
    venv.EnvBuilder(with_pip=True, clear=True).create(str(venv_dir))


def install_and_smoke_test_artifact(artifact_label, artifact_path, *, work_root, expected_version):
    env_dir = Path(work_root) / f"{artifact_label}-smoke-env"
    create_virtualenv(env_dir)

    env_python = venv_python_path(env_dir)
    cli_path = venv_cli_path(env_dir)

    _run([str(env_python), "-m", "pip", "install", str(artifact_path)], cwd=ROOT)

    if not cli_path.exists():
        raise RuntimeError(
            f"Python packaging smoke failed: expected CLI entry point was not installed: {cli_path}"
        )

    version_output = _run([str(cli_path), "--version"], cwd=ROOT)
    if expected_version not in version_output:
        raise RuntimeError(
            f"Python packaging smoke failed: installed CLI version output did not include {expected_version!r}"
        )

    import_output = _run(
        [str(env_python), "-c", "import wechat_cli; print(wechat_cli.__version__)"],
        cwd=ROOT,
    ).strip()
    if import_output != expected_version:
        raise RuntimeError(
            "Python packaging smoke failed: installed module version mismatch: "
            f"{import_output!r} != {expected_version!r}"
        )

    help_output = _run([str(cli_path), "--help"], cwd=ROOT)
    if "session-updates" not in help_output:
        raise RuntimeError(
            "Python packaging smoke failed: installed CLI help output is missing expected commands"
        )

    print(f"[+] Install smoke passed for {artifact_label}: {artifact_path.name}")


def run_install_smoke(artifacts, *, work_root, expected_version):
    for artifact_label in ("wheel", "sdist"):
        install_and_smoke_test_artifact(
            artifact_label,
            artifacts[artifact_label],
            work_root=work_root,
            expected_version=expected_version,
        )


def main():
    assert_release_metadata()
    print("[+] Python release metadata is aligned")

    with tempfile.TemporaryDirectory(prefix="wechat-cli-package-smoke-") as tmpdir:
        tmp_root = Path(tmpdir)
        artifacts = build_python_package(tmp_root / "python")
        run_install_smoke(artifacts, work_root=tmp_root, expected_version=_read_expected_version())

    print("[+] Python packaging smoke checks passed")


def _read_expected_version():
    package_init = ROOT / "wechat_cli" / "__init__.py"
    for line in package_init.read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__ = "):
            return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError(f"Unable to read __version__ from {package_init}")


if __name__ == "__main__":
    main()
