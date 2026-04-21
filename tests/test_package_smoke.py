import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


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

    def test_venv_cli_path_matches_current_platform_layout(self):
        venv_dir = Path("C:/tmp/demo-env") if sys.platform == "win32" else Path("/tmp/demo-env")
        cli_path = package_smoke.venv_cli_path(venv_dir)
        expected_name = "wechat-cli.exe" if sys.platform == "win32" else "wechat-cli"
        self.assertEqual(cli_path.name, expected_name)


if __name__ == "__main__":
    unittest.main()
