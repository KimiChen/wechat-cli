import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
CHECK_TAG_SCRIPT = SCRIPTS_DIR / "check_release_tag.py"
sys.path.insert(0, str(SCRIPTS_DIR))


def _load_script_module(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


build_release_artifacts = _load_script_module("build_release_artifacts")


class GitHubReleaseTests(unittest.TestCase):
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

    def _run_check_tag(self, root, *args):
        return subprocess.run(
            [sys.executable, str(CHECK_TAG_SCRIPT), "--root", str(root), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    def test_check_release_tag_accepts_matching_tag(self):
        root = self._create_fixture(pyproject_version="1.2.3", package_version="1.2.3")

        result = self._run_check_tag(root, "v1.2.3")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Release tag matches Python package version", result.stdout)

    def test_check_release_tag_rejects_invalid_format(self):
        root = self._create_fixture(pyproject_version="1.2.3", package_version="1.2.3")

        result = self._run_check_tag(root, "1.2.3")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must match the format v<version>", result.stderr)

    def test_check_release_tag_rejects_mismatched_tag(self):
        root = self._create_fixture(pyproject_version="1.2.3", package_version="1.2.3")

        result = self._run_check_tag(root, "v1.2.4")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match pyproject.toml version", result.stderr)

    def test_check_release_tag_rejects_misaligned_versions(self):
        root = self._create_fixture(pyproject_version="1.2.3", package_version="1.2.2")

        result = self._run_check_tag(root, "v1.2.3")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Current versions are misaligned", result.stderr)

    def test_check_release_tag_can_print_expected_tag(self):
        root = self._create_fixture(pyproject_version="1.2.3", package_version="1.2.3")

        result = self._run_check_tag(root, "--print-expected-tag")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "v1.2.3")

    def test_write_sha256sums_writes_expected_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            wheel = root / "wechat_cli-0.2.4-py3-none-any.whl"
            sdist = root / "wechat_cli-0.2.4.tar.gz"
            output = root / "SHA256SUMS"
            wheel.write_text("wheel", encoding="utf-8")
            sdist.write_text("sdist", encoding="utf-8")

            build_release_artifacts.write_sha256sums([wheel, sdist], output)

            content = output.read_text(encoding="utf-8")
            self.assertIn(f"{build_release_artifacts.sha256_digest(wheel)}  {wheel.name}", content)
            self.assertIn(f"{build_release_artifacts.sha256_digest(sdist)}  {sdist.name}", content)
            self.assertTrue(content.endswith("\n"))

    def test_build_release_artifacts_replaces_stale_dist_outputs(self):
        root = self._create_fixture(pyproject_version="1.2.3", package_version="1.2.3")
        output_dir = root / "dist"
        output_dir.mkdir()
        stale_wheel = output_dir / "wechat_cli-1.2.2-py3-none-any.whl"
        stale_sdist = output_dir / "wechat_cli-1.2.2.tar.gz"
        keep_file = output_dir / "notes.txt"
        stale_wheel.write_text("stale wheel", encoding="utf-8")
        stale_sdist.write_text("stale sdist", encoding="utf-8")
        keep_file.write_text("keep me", encoding="utf-8")

        def _fake_build(cmd, *, cwd, check):
            self.assertEqual(cwd, root)
            self.assertTrue(check)
            staging_dir = Path(cmd[cmd.index("--outdir") + 1])
            (staging_dir / "wechat_cli-1.2.3-py3-none-any.whl").write_text(
                "fresh wheel",
                encoding="utf-8",
            )
            (staging_dir / "wechat_cli-1.2.3.tar.gz").write_text(
                "fresh sdist",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(cmd, 0)

        with mock.patch.object(build_release_artifacts.subprocess, "run", side_effect=_fake_build):
            artifacts = build_release_artifacts.build_release_artifacts(root, output_dir)

        self.assertEqual(
            artifacts["wheel"],
            output_dir / "wechat_cli-1.2.3-py3-none-any.whl",
        )
        self.assertEqual(
            artifacts["sdist"],
            output_dir / "wechat_cli-1.2.3.tar.gz",
        )
        self.assertFalse(stale_wheel.exists())
        self.assertFalse(stale_sdist.exists())
        self.assertTrue(keep_file.exists())

    def test_release_workflow_publishes_tagged_github_release(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        for snippet in (
            'tags:\n      - "v*"',
            'python-version: "3.14"',
            "python -m pip install -e .",
            'python scripts/prepare_release.py --tag "${GITHUB_REF_NAME}"',
            "python scripts/build_release_artifacts.py --outdir dist",
            "dist/SHA256SUMS",
            "gh release create",
            "gh release upload",
            "contents: write",
        ):
            self.assertIn(snippet, workflow)


if __name__ == "__main__":
    unittest.main()
