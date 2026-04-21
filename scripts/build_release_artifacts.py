#!/usr/bin/env python3
"""Build GitHub Release artifacts and write SHA256SUMS."""

import argparse
import subprocess
import sys
from pathlib import Path

from check_release_tag import read_versions
from package_smoke import collect_python_artifacts, sha256_digest, validate_artifact_filenames


ROOT = Path(__file__).resolve().parents[1]


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Build release artifacts into dist/ and write SHA256SUMS.",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("dist"),
        help="Output directory for built artifacts. Relative paths are resolved from the repo root.",
    )
    parser.add_argument(
        "--sha256-file",
        default="SHA256SUMS",
        help="Filename to write inside the output directory. Defaults to SHA256SUMS.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root to build. Defaults to the current repository.",
    )
    return parser.parse_args()


def _resolve_output_dir(root, outdir):
    outdir = Path(outdir)
    if outdir.is_absolute():
        return outdir
    return Path(root) / outdir


def _assert_release_metadata(root):
    versions = read_versions(root)
    project_version = versions["python_project_version"]
    cli_version = versions["python_cli_version"]
    if cli_version != project_version:
        raise RuntimeError(
            "Current versions are misaligned. "
            f"pyproject.toml={project_version}, wechat_cli/__init__.py={cli_version}"
        )
    return project_version


def build_release_artifacts(root, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--sdist",
            "--wheel",
            "--outdir",
            str(output_dir),
        ],
        cwd=Path(root),
        check=True,
    )
    return collect_python_artifacts(output_dir)


def write_sha256sums(paths, output_path):
    lines = [f"{sha256_digest(path)}  {path.name}" for path in sorted(paths, key=lambda path: path.name)]
    output_path = Path(output_path)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def main():
    args = _parse_args()
    root = Path(args.root).resolve()
    output_dir = _resolve_output_dir(root, args.outdir)
    version = _assert_release_metadata(root)

    artifacts = build_release_artifacts(root, output_dir)
    validate_artifact_filenames(artifacts, version)

    checksum_path = write_sha256sums(artifacts.values(), output_dir / args.sha256_file)
    print("[+] Built release artifacts:")
    for artifact in sorted(artifacts.values(), key=lambda path: path.name):
        print(f"[+]   {artifact.name}")
    print(f"[+] Wrote checksums: {checksum_path}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"[-] {exc}", file=sys.stderr)
        sys.exit(1)
