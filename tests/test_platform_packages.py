import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_platform_packages.py"


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class PlatformPackageValidationTests(unittest.TestCase):
    def _create_repo_fixture(self):
        tmpdir = tempfile.TemporaryDirectory()
        root = Path(tmpdir.name)
        metadata = {
            "root_package": "@canghe_ai/wechat-cli",
            "platform_packages": {
                "linux-x64": "@canghe_ai/wechat-cli-linux-x64",
                "win32-x64": "@canghe_ai/wechat-cli-win32-x64",
            },
        }
        _write_json(root / "npm" / "wechat-cli" / "package-metadata.json", metadata)

        for platform_key, package_name in metadata["platform_packages"].items():
            os_name, cpu_arch = platform_key.split("-", 1)
            _write_json(
                root / "npm" / "platforms" / platform_key / "package.json",
                {
                    "name": package_name,
                    "version": "0.2.4",
                    "os": [os_name],
                    "cpu": [cpu_arch],
                    "files": ["bin/"],
                },
            )

        self.addCleanup(tmpdir.cleanup)
        return root

    def _run_script(self, root, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), *args],
            capture_output=True,
            text=True,
        )

    def test_manifest_only_validation_passes_without_binaries(self):
        root = self._create_repo_fixture()

        result = self._run_script(root)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("manifest-only mode", result.stdout)

    def test_strict_validation_requires_expected_binaries(self):
        root = self._create_repo_fixture()

        result = self._run_script(root, "--require-binaries")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing platform binary for linux-x64", result.stdout + result.stderr)
        self.assertIn("Missing platform binary for win32-x64", result.stdout + result.stderr)

    def test_strict_validation_passes_when_all_binaries_exist(self):
        root = self._create_repo_fixture()

        linux_binary = root / "npm" / "platforms" / "linux-x64" / "bin" / "wechat-cli"
        linux_binary.parent.mkdir(parents=True, exist_ok=True)
        linux_binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

        win_binary = root / "npm" / "platforms" / "win32-x64" / "bin" / "wechat-cli.exe"
        win_binary.parent.mkdir(parents=True, exist_ok=True)
        win_binary.write_bytes(b"MZ")

        result = self._run_script(root, "--require-binaries")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("strict mode", result.stdout)

    def test_validation_rejects_os_cpu_mismatch(self):
        root = self._create_repo_fixture()
        _write_json(
            root / "npm" / "platforms" / "linux-x64" / "package.json",
            {
                "name": "@canghe_ai/wechat-cli-linux-x64",
                "version": "0.2.4",
                "os": ["linux"],
                "cpu": ["arm64"],
                "files": ["bin/"],
            },
        )

        result = self._run_script(root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Platform package cpu mismatch for linux-x64", result.stdout + result.stderr)
