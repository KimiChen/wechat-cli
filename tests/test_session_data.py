import os
import sqlite3
import tempfile
import unittest

import zstandard as zstd

from wechat_cli.core import session_data


class FakeCache:
    def __init__(self, db_path=None):
        self.db_path = db_path

    def get(self, rel_key):
        if rel_key == os.path.join("session", "session.db"):
            return self.db_path
        return None


def _create_session_db(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE SessionTable ("
            "username TEXT, "
            "unread_count INTEGER, "
            "summary BLOB, "
            "last_timestamp INTEGER, "
            "last_msg_type INTEGER, "
            "last_msg_sender TEXT, "
            "last_sender_display_name TEXT)"
        )
        conn.executemany(
            "INSERT INTO SessionTable VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


class SessionDataTests(unittest.TestCase):
    def test_query_session_rows_filters_and_orders_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "session", "session.db")
            _create_session_db(
                db_path,
                [
                    ("chat_a", 0, "hello", 100, 1, "", ""),
                    ("chat_b", 3, "world", 300, 1, "", ""),
                    ("chat_c", 1, "again", 200, 1, "", ""),
                ],
            )
            rows = session_data.query_session_rows(
                FakeCache(db_path),
                where_clause="unread_count > 0",
                limit=2,
            )

        self.assertEqual([row[0] for row in rows], ["chat_b", "chat_c"])

    def test_session_row_to_entry_normalizes_group_summary_and_sender(self):
        summary = zstd.ZstdCompressor().compress("alice:\nhello".encode("utf-8"))
        row = (
            "team@chatroom",
            2,
            summary,
            1_700_000_000,
            1,
            "alice",
            "Alice Sender",
        )
        names = {
            "team@chatroom": "Team",
            "alice": "Alice",
        }

        entry = session_data.session_row_to_entry(row, names)

        self.assertEqual(entry["chat"], "Team")
        self.assertEqual(entry["sender"], "Alice")
        self.assertEqual(entry["last_message"], "hello")
        self.assertEqual(entry["msg_type"], "文本")
        self.assertEqual(entry["unread"], 2)

    def test_get_session_db_path_raises_helpful_error_when_missing(self):
        with self.assertRaises(session_data.SessionDBError):
            session_data.get_session_db_path(FakeCache())


if __name__ == "__main__":
    unittest.main()
