import unittest
from unittest import mock

from wechat_cli.core import config


class ConfigSelectionTests(unittest.TestCase):
    def test_choose_candidate_prefers_most_recent_when_non_interactive(self):
        candidates = ["older", "newer"]
        with mock.patch.object(config, "_candidate_mtime", side_effect=lambda path: {"older": 1, "newer": 2}[path]):
            with mock.patch.object(config.sys.stdin, "isatty", return_value=False):
                with mock.patch("builtins.print"):
                    selected = config._choose_candidate(candidates)
        self.assertEqual(selected, "newer")

    def test_choose_candidate_empty_input_selects_most_recent(self):
        candidates = ["older", "newer"]
        with mock.patch.object(config, "_candidate_mtime", side_effect=lambda path: {"older": 1, "newer": 2}[path]):
            with mock.patch.object(config.sys.stdin, "isatty", return_value=True):
                with mock.patch("builtins.input", return_value=""):
                    with mock.patch("builtins.print"):
                        selected = config._choose_candidate(candidates)
        self.assertEqual(selected, "newer")

    def test_load_config_sets_decrypted_cache_policy_defaults(self):
        with mock.patch.object(config.os.path, "exists", return_value=True):
            with mock.patch("builtins.open", mock.mock_open(read_data='{"db_dir":"db_storage"}')):
                cfg = config.load_config("C:/tmp/config.json")

        self.assertEqual(cfg["decrypted_cache_ttl_hours"], config.DEFAULT_DECRYPTED_CACHE_TTL_HOURS)
        self.assertFalse(cfg["persist_decrypted_cache"])

    def test_load_config_normalizes_decrypted_cache_policy_values(self):
        raw_config = {
            "db_dir": "db_storage",
            "persist_decrypted_cache": "true",
            "decrypted_cache_ttl_hours": "-5",
        }
        with mock.patch.object(config.os.path, "exists", return_value=True):
            with mock.patch("builtins.open", mock.mock_open(read_data='{"db_dir":"db_storage","persist_decrypted_cache":"true","decrypted_cache_ttl_hours":"-5"}')):
                cfg = config.load_config("C:/tmp/config.json")

        self.assertTrue(cfg["persist_decrypted_cache"])
        self.assertEqual(cfg["decrypted_cache_ttl_hours"], config.DEFAULT_DECRYPTED_CACHE_TTL_HOURS)


if __name__ == "__main__":
    unittest.main()
