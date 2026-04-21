import unittest
from unittest import mock

from wechat_cli.keys import scanner_macos


class ScannerMacOSTests(unittest.TestCase):
    def test_get_original_entitlements_ignores_expected_subprocess_errors(self):
        with mock.patch.object(
            scanner_macos.subprocess,
            "run",
            side_effect=OSError("codesign missing"),
        ):
            entitlements = scanner_macos._get_original_entitlements("/Applications/WeChat.app")

        self.assertIsNone(entitlements)

    def test_get_original_entitlements_ignores_invalid_plist_output(self):
        result = mock.Mock(returncode=0, stdout=b"not-a-plist")
        with mock.patch.object(scanner_macos.subprocess, "run", return_value=result):
            entitlements = scanner_macos._get_original_entitlements("/Applications/WeChat.app")

        self.assertIsNone(entitlements)

    def test_get_original_entitlements_propagates_unexpected_errors(self):
        result = mock.Mock(returncode=0, stdout=b"plist-data")
        with mock.patch.object(scanner_macos.subprocess, "run", return_value=result):
            with mock.patch.object(
                scanner_macos.plistlib,
                "loads",
                side_effect=RuntimeError("unexpected plist bug"),
            ):
                with self.assertRaisesRegex(RuntimeError, "unexpected plist bug"):
                    scanner_macos._get_original_entitlements("/Applications/WeChat.app")

    def test_resign_wechat_reports_expected_entitlement_build_errors(self):
        with mock.patch("builtins.print"):
            with mock.patch.object(
                scanner_macos.os.path,
                "isdir",
                side_effect=lambda path: path == "/Applications/WeChat.app",
            ):
                with mock.patch.object(
                    scanner_macos,
                    "_build_entitlements_xml",
                    side_effect=OSError("permission denied"),
                ):
                    ok, err = scanner_macos._resign_wechat()

        self.assertFalse(ok)
        self.assertEqual(err, "提取微信原始权限失败: permission denied")

    def test_resign_wechat_propagates_unexpected_entitlement_build_errors(self):
        with mock.patch("builtins.print"):
            with mock.patch.object(
                scanner_macos.os.path,
                "isdir",
                side_effect=lambda path: path == "/Applications/WeChat.app",
            ):
                with mock.patch.object(
                    scanner_macos,
                    "_build_entitlements_xml",
                    side_effect=RuntimeError("unexpected build bug"),
                ):
                    with self.assertRaisesRegex(RuntimeError, "unexpected build bug"):
                        scanner_macos._resign_wechat()


if __name__ == "__main__":
    unittest.main()
