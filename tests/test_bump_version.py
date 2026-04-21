import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "bump_version.py"


class BumpVersionScriptTests(unittest.TestCase):
    def _create_fixture(self, *, pyproject_version="0.2.4", package_version="0.2.4"):
        tmpdir = tempfile.TemporaryDirectory()
        root = Path(tmpdir.name)
        (root / "wechat_cli").mkdir(parents=True, exist_ok=True)
        (root / "pyproject.toml").write_text(
            "\n".join(
                [
                    "[project]",
                    'name = "wechat-cli"',
                    f'version = "{pyproject_version}"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (root / "wechat_cli" / "__init__.py").write_text(
            f'__version__ = "{package_version}"\n',
            encoding="utf-8",
        )
        self.addCleanup(tmpdir.cleanup)
        return root

    def _run(self, root, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    def test_print_current_outputs_aligned_version(self):
        root = self._create_fixture(pyproject_version="1.2.3", package_version="1.2.3")

        result = self._run(root, "--print-current")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "1.2.3")

    def test_updates_both_version_files(self):
        root = self._create_fixture()

        result = self._run(root, "0.2.5")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Version change: 0.2.4 -> 0.2.5", result.stdout)
        self.assertIn('version = "0.2.5"', (root / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertIn('__version__ = "0.2.5"', (root / "wechat_cli" / "__init__.py").read_text(encoding="utf-8"))

    def test_dry_run_does_not_modify_files(self):
        root = self._create_fixture()
        original_pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        original_init = (root / "wechat_cli" / "__init__.py").read_text(encoding="utf-8")

        result = self._run(root, "0.2.5", "--dry-run")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Would update", result.stdout)
        self.assertEqual((root / "pyproject.toml").read_text(encoding="utf-8"), original_pyproject)
        self.assertEqual((root / "wechat_cli" / "__init__.py").read_text(encoding="utf-8"), original_init)

    def test_rejects_misaligned_versions_without_override(self):
        root = self._create_fixture(pyproject_version="0.2.4", package_version="0.2.3")

        result = self._run(root, "0.2.5")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Current versions are misaligned", result.stderr)

    def test_can_update_misaligned_versions_with_override(self):
        root = self._create_fixture(pyproject_version="0.2.4", package_version="0.2.3")

        result = self._run(root, "0.2.5", "--allow-misaligned")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Version change: misaligned -> 0.2.5", result.stdout)
        self.assertIn('version = "0.2.5"', (root / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertIn('__version__ = "0.2.5"', (root / "wechat_cli" / "__init__.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
