#!/usr/bin/env python3
"""Run lightweight packaging smoke checks for Python artifacts."""

import hashlib
import os
import subprocess
import sys
import tempfile
import tarfile
import venv
from pathlib import Path
import zipfile

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


def expected_artifact_names(version):
    return {
        "sdist": f"wechat_cli-{version}.tar.gz",
        "wheel": f"wechat_cli-{version}-py3-none-any.whl",
    }


def validate_artifact_filenames(artifacts, version):
    expected = expected_artifact_names(version)
    for artifact_label, expected_name in expected.items():
        actual_name = artifacts[artifact_label].name
        if actual_name != expected_name:
            raise RuntimeError(
                "Python packaging smoke failed: unexpected artifact filename for "
                f"{artifact_label}: {actual_name!r} != {expected_name!r}"
            )


def sha256_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_sdist_members(version):
    root = f"wechat_cli-{version}"
    return {
        f"{root}/README.md",
        f"{root}/LICENSE",
        f"{root}/pyproject.toml",
        f"{root}/wechat_cli/__init__.py",
        f"{root}/wechat_cli/main.py",
        f"{root}/wechat_cli/bin/find_all_keys_macos.arm64",
        f"{root}/wechat_cli/bin/find_all_keys_macos.c",
        f"{root}/wechat_cli/commands/session_updates.py",
        f"{root}/wechat_cli/core/session_updates.py",
    }


def _required_wheel_members(version):
    dist_info = f"wechat_cli-{version}.dist-info"
    return {
        "wechat_cli/__init__.py",
        "wechat_cli/main.py",
        "wechat_cli/bin/find_all_keys_macos.arm64",
        "wechat_cli/bin/find_all_keys_macos.c",
        "wechat_cli/commands/session_updates.py",
        "wechat_cli/core/session_updates.py",
        f"{dist_info}/METADATA",
        f"{dist_info}/WHEEL",
        f"{dist_info}/entry_points.txt",
        f"{dist_info}/top_level.txt",
        f"{dist_info}/RECORD",
        f"{dist_info}/licenses/LICENSE",
    }


def validate_sdist_members(members, version):
    member_set = set(members)
    missing = sorted(_required_sdist_members(version) - member_set)
    if missing:
        raise RuntimeError(
            "Python packaging smoke failed: sdist is missing expected files: "
            + ", ".join(missing)
        )


def validate_wheel_members(members, version):
    member_set = set(members)
    missing = sorted(_required_wheel_members(version) - member_set)
    if missing:
        raise RuntimeError(
            "Python packaging smoke failed: wheel is missing expected files: "
            + ", ".join(missing)
        )


def inspect_artifact_layouts(artifacts, version):
    validate_artifact_filenames(artifacts, version)

    with tarfile.open(artifacts["sdist"], "r:gz") as archive:
        validate_sdist_members(archive.getnames(), version)

    with zipfile.ZipFile(artifacts["wheel"]) as archive:
        validate_wheel_members(archive.namelist(), version)

    for artifact_label, artifact_path in artifacts.items():
        print(f"[+] {artifact_label} sha256: {sha256_digest(artifact_path)}  {artifact_path.name}")


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
        expected_version = _read_expected_version()
        artifacts = build_python_package(tmp_root / "python")
        inspect_artifact_layouts(artifacts, expected_version)
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
