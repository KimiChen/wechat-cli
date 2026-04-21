#!/usr/bin/env python3
"""Validate Python release metadata stays aligned."""

import ast
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
PYTHON_PACKAGE_INIT = ROOT / "wechat_cli" / "__init__.py"


def _read_pyproject():
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)


def _read_python_cli_version():
    source = PYTHON_PACKAGE_INIT.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(PYTHON_PACKAGE_INIT))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__version__":
                value = ast.literal_eval(node.value)
                if isinstance(value, str):
                    return value
                break
    raise RuntimeError(f"Unable to read __version__ from {PYTHON_PACKAGE_INIT}")


def collect_release_metadata():
    pyproject = _read_pyproject()
    return {
        "python_project_version": pyproject["project"]["version"],
        "python_cli_version": _read_python_cli_version(),
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
