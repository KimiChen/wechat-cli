import json
import os
import tempfile
import unittest
from unittest import mock

from wechat_cli.core import session_updates


class SessionUpdatesTests(unittest.TestCase):
    def test_collect_session_updates_first_call_returns_unread_session_snapshot(self):
        rows = [
            ("room@chatroom", 3, "alice:\nhello", 1_700_000_000, 1, "alice", "Alice Sender"),
            ("bob", 0, "done", 1_700_000_100, 1, "", ""),
        ]
        names = {
            "room@chatroom": "Team",
            "alice": "Alice",
            "bob": "Bob",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "last_check.json")
            with mock.patch.object(session_updates, "query_session_rows", return_value=rows):
                with mock.patch.object(session_updates, "get_contact_names", return_value=names):
                    result = session_updates.collect_session_updates(
                        cache=object(),
                        decrypted_dir="ignored",
                        state_file=state_file,
                    )

            self.assertTrue(os.path.exists(state_file))
            with open(state_file, encoding="utf-8") as f:
                saved = json.load(f)

        self.assertTrue(result["first_call"])
        self.assertEqual(result["scope"], "会话更新")
        self.assertEqual(result["stream_type"], "session_updates")
        self.assertEqual(result["tracked_by"], "session_last_timestamp")
        self.assertEqual(result["snapshot_kind"], "initial_unread_sessions")
        self.assertEqual(result["unread_count"], 1)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["messages"][0]["chat"], "Team")
        self.assertEqual(saved, {"room@chatroom": 1_700_000_000, "bob": 1_700_000_100})

    def test_collect_session_updates_subsequent_call_returns_changed_sessions(self):
        rows = [
            ("alice", 0, "hello", 1_700_000_200, 1, "", ""),
            ("bob", 1, "later", 1_700_000_050, 1, "", ""),
        ]
        names = {"alice": "Alice", "bob": "Bob"}

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "last_check.json")
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump({"alice": 1_700_000_100, "bob": 1_700_000_050}, f)

            with mock.patch.object(session_updates, "query_session_rows", return_value=rows):
                with mock.patch.object(session_updates, "get_contact_names", return_value=names):
                    result = session_updates.collect_session_updates(
                        cache=object(),
                        decrypted_dir="ignored",
                        state_file=state_file,
                    )

        self.assertFalse(result["first_call"])
        self.assertEqual(result["snapshot_kind"], "changed_sessions_since_last_check")
        self.assertEqual(result["new_count"], 1)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["messages"][0]["chat"], "Alice")

    def test_format_session_updates_text_marks_session_level_semantics(self):
        text = session_updates.format_session_updates_text(
            {
                "first_call": False,
                "messages": [],
            }
        )
        self.assertIn("会话级更新", text)
        self.assertIn("不是逐条消息流", text)


if __name__ == "__main__":
    unittest.main()
