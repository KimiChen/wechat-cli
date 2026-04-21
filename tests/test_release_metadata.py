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

    def test_readme_mentions_published_npm_package_name(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("npm install -g @canghe_ai/wechat-cli", readme)

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
            "package_smoke.py",
        ):
            self.assertIn(snippet, guide)

    def test_npm_wrappers_use_shared_package_metadata_file(self):
        install_js = (ROOT / "npm" / "wechat-cli" / "install.js").read_text(encoding="utf-8")
        wrapper_js = (ROOT / "npm" / "wechat-cli" / "bin" / "wechat-cli.js").read_text(encoding="utf-8")
        self.assertIn("require('./package-metadata.json')", install_js)
        self.assertIn("require('../package-metadata.json')", wrapper_js)


if __name__ == "__main__":
    unittest.main()
