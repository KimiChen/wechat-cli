import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare_release.py"


class PrepareReleaseScriptTests(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    def test_dry_run_lists_python_only_release_steps(self):
        result = self._run("--dry-run")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = result.stdout
        self.assertIn("Python-only packaging workflow", output)
        self.assertIn("-m unittest discover -s tests -v", output)
        self.assertIn("-m compileall wechat_cli tests scripts", output)
        self.assertIn("scripts/package_smoke.py", output)

    def test_dry_run_includes_release_tag_validation_when_requested(self):
        result = self._run("--dry-run", "--tag", "v0.2.4")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("scripts/check_release_tag.py v0.2.4", result.stdout)

    def test_dry_run_respects_skip_flags(self):
        result = self._run("--dry-run", "--skip-tests", "--skip-package-smoke")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = result.stdout
        self.assertNotIn("-m unittest discover -s tests -v", output)
        self.assertIn("-m compileall wechat_cli tests scripts", output)
        self.assertNotIn("scripts/package_smoke.py", output)

    def test_dry_run_reports_when_all_steps_are_skipped(self):
        result = self._run(
            "--dry-run",
            "--skip-tests",
            "--skip-compileall",
            "--skip-package-smoke",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("No commands selected", result.stdout)
