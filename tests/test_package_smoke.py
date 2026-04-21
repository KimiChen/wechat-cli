import importlib.util
import tarfile
import sys
import tempfile
import unittest
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

spec = importlib.util.spec_from_file_location("package_smoke", SCRIPTS_DIR / "package_smoke.py")
package_smoke = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(package_smoke)


class PackageSmokeTests(unittest.TestCase):
    def test_collect_python_artifacts_returns_expected_mapping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            wheel = root / "wechat_cli-0.2.4-py3-none-any.whl"
            sdist = root / "wechat_cli-0.2.4.tar.gz"
            wheel.write_text("wheel", encoding="utf-8")
            sdist.write_text("sdist", encoding="utf-8")

            artifacts = package_smoke.collect_python_artifacts(root)

            self.assertEqual(artifacts["wheel"], wheel)
            self.assertEqual(artifacts["sdist"], sdist)

    def test_collect_python_artifacts_requires_both_wheel_and_sdist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "wechat_cli-0.2.4-py3-none-any.whl").write_text("wheel", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "missing expected artifacts"):
                package_smoke.collect_python_artifacts(root)

    def test_validate_artifact_filenames_requires_expected_names(self):
        artifacts = {
            "wheel": Path("dist/wechat_cli-0.2.4-py3-none-any.whl"),
            "sdist": Path("dist/not-the-right-name.tar.gz"),
        }

        with self.assertRaisesRegex(RuntimeError, "unexpected artifact filename"):
            package_smoke.validate_artifact_filenames(artifacts, "0.2.4")

    def test_sha256_digest_matches_known_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "demo.txt"
            path.write_text("wechat-cli\n", encoding="utf-8")

            self.assertEqual(
                package_smoke.sha256_digest(path),
                "9c9f0d997a6ff50b1de6629ab4c10dff931a4c01c8c67500c9a22fcf062b6822",
            )

    def test_validate_sdist_members_requires_expected_files(self):
        members = {
            "wechat_cli-0.2.4/README.md",
            "wechat_cli-0.2.4/LICENSE",
        }

        with self.assertRaisesRegex(RuntimeError, "sdist is missing expected files"):
            package_smoke.validate_sdist_members(members, "0.2.4")

    def test_validate_wheel_members_requires_expected_files(self):
        members = {
            "wechat_cli/__init__.py",
            "wechat_cli/main.py",
        }

        with self.assertRaisesRegex(RuntimeError, "wheel is missing expected files"):
            package_smoke.validate_wheel_members(members, "0.2.4")

    def test_inspect_artifact_layouts_accepts_valid_archives(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            version = "0.2.4"
            wheel = root / f"wechat_cli-{version}-py3-none-any.whl"
            sdist = root / f"wechat_cli-{version}.tar.gz"

            with tarfile.open(sdist, "w:gz") as archive:
                for name in sorted(package_smoke._required_sdist_members(version)):
                    file_path = root / name.replace("/", "_")
                    file_path.write_text(name, encoding="utf-8")
                    archive.add(file_path, arcname=name)

            with zipfile.ZipFile(wheel, "w") as archive:
                for name in sorted(package_smoke._required_wheel_members(version)):
                    archive.writestr(name, name)

            package_smoke.inspect_artifact_layouts(
                {"wheel": wheel, "sdist": sdist},
                version,
            )

    def test_venv_cli_path_matches_current_platform_layout(self):
        venv_dir = Path("C:/tmp/demo-env") if sys.platform == "win32" else Path("/tmp/demo-env")
        cli_path = package_smoke.venv_cli_path(venv_dir)
        expected_name = "wechat-cli.exe" if sys.platform == "win32" else "wechat-cli"
        self.assertEqual(cli_path.name, expected_name)


if __name__ == "__main__":
    unittest.main()
