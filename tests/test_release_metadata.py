import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_release_metadata_script_passes(self):
        result = subprocess.run(
            [sys.executable, "scripts/check_release_metadata.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Release metadata is aligned", result.stdout)

    def test_release_metadata_script_passes_in_isolated_mode(self):
        result = subprocess.run(
            [sys.executable, "-I", "scripts/check_release_metadata.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Release metadata is aligned", result.stdout)

    def test_readme_describes_python_only_installation(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("pip install -e .", readme)
        self.assertIn("构建 Python 包", readme)

    def test_readme_links_developer_guide(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/development.md", readme)
        self.assertTrue((ROOT / "docs" / "development.md").exists())

    def test_developer_guide_covers_cache_and_release_topics(self):
        guide = (ROOT / "docs" / "development.md").read_text(encoding="utf-8")
        for snippet in (
            "persist_decrypted_cache",
            "decrypted_cache_ttl_hours",
            "session-updates",
            "bump_version.py",
            "安装 smoke",
            "sha256",
            "package_smoke.py",
            "prepare_release.py",
        ):
            self.assertIn(snippet, guide)

    def test_ci_package_smoke_is_python_only(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("Python Package Smoke", workflow)
        self.assertIn('python-version:\n          - "3.10"', workflow)
        self.assertIn('- "3.11"', workflow)
        self.assertIn('- "3.12"', workflow)
        self.assertIn("python scripts/package_smoke.py", workflow)
        self.assertIn("python -m pip install build", workflow)


if __name__ == "__main__":
    unittest.main()
