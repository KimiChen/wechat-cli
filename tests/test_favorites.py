import os
import sqlite3
import tempfile
import unittest

from wechat_cli.core import favorites


class FakeCache:
    def __init__(self, db_path=None):
        self.db_path = db_path

    def get(self, rel_key):
        if rel_key == os.path.join("favorite", "favorite.db"):
            return self.db_path
        return None


def _create_favorite_db(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE fav_db_item ("
            "local_id INTEGER, "
            "type INTEGER, "
            "update_time INTEGER, "
            "content TEXT, "
            "fromusr TEXT, "
            "realchatname TEXT)"
        )
        conn.executemany(
            "INSERT INTO fav_db_item VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


class FavoriteServiceTests(unittest.TestCase):
    def test_list_favorites_formats_and_filters_rows(self):
        article_xml = (
            "<favitem><appmsg><pagetitle>Network</pagetitle>"
            "<pagedesc>TCP/IP</pagedesc></appmsg></favitem>"
        )
        text_xml = "<favitem><desc>Hello world</desc></favitem>"

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "favorite", "favorite.db")
            _create_favorite_db(
                db_path,
                [
                    (1, 1, 1_700_000_000, text_xml, "alice", "room@chatroom"),
                    (2, 5, 1_700_000_100, article_xml, "bob", ""),
                ],
            )

            result = favorites.list_favorites(
                FakeCache(db_path),
                os.path.join(tmpdir, "missing"),
                {"alice": "Alice", "bob": "Bob", "room@chatroom": "Team"},
                limit=5,
                favorite_type="article",
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "文章")
        self.assertEqual(result[0]["summary"], "Network - TCP/IP")
        self.assertEqual(result[0]["from"], "Bob")
        self.assertEqual(result[0]["source_chat"], "")

    def test_list_favorites_raises_helpful_error_when_missing(self):
        with self.assertRaises(favorites.FavoriteDBError):
            favorites.list_favorites(FakeCache(), "missing", {}, limit=1)


if __name__ == "__main__":
    unittest.main()
