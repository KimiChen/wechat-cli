import os
import sqlite3
import tempfile
import unittest

from wechat_cli.core import contacts


class FakeCache:
    def __init__(self, db_path):
        self.db_path = db_path

    def get(self, rel_key):
        if rel_key == os.path.join("contact", "contact.db"):
            return self.db_path
        return None


def _create_contact_db(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE contact ("
            "id INTEGER PRIMARY KEY, "
            "username TEXT, "
            "nick_name TEXT, "
            "remark TEXT, "
            "alias TEXT, "
            "description TEXT, "
            "small_head_url TEXT, "
            "big_head_url TEXT, "
            "verify_flag INTEGER, "
            "local_type INTEGER)"
        )
        conn.execute("CREATE TABLE chat_room (id INTEGER PRIMARY KEY, owner TEXT)")
        conn.execute("CREATE TABLE chatroom_member (room_id INTEGER, member_id INTEGER)")
        for index, row in enumerate(rows, start=1):
            conn.execute(
                "INSERT INTO contact "
                "(id, username, nick_name, remark, alias, description, small_head_url, big_head_url, verify_flag, local_type) "
                "VALUES (?, ?, ?, ?, '', '', '', '', 0, 0)",
                (index, row["username"], row.get("nick_name", ""), row.get("remark", "")),
            )
        conn.commit()
    finally:
        conn.close()


class ContactsCacheTests(unittest.TestCase):
    def test_contact_cache_is_isolated_per_cache_instance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db1 = os.path.join(tmpdir, "a", "contact.db")
            db2 = os.path.join(tmpdir, "b", "contact.db")
            _create_contact_db(
                db1,
                [{"username": "alice", "nick_name": "Alice"}],
            )
            _create_contact_db(
                db2,
                [{"username": "bob", "nick_name": "Bob"}],
            )

            cache1 = FakeCache(db1)
            cache2 = FakeCache(db2)

            names1 = contacts.get_contact_names(cache1, os.path.join(tmpdir, "missing-1"))
            names2 = contacts.get_contact_names(cache2, os.path.join(tmpdir, "missing-2"))

            self.assertEqual(names1, {"alice": "Alice"})
            self.assertEqual(names2, {"bob": "Bob"})
            self.assertNotEqual(names1, names2)
            self.assertTrue(hasattr(cache1, "_contacts_state"))
            self.assertTrue(hasattr(cache2, "_contacts_state"))

    def test_self_username_is_cached_per_db_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "contact", "contact.db")
            _create_contact_db(
                db_path,
                [{"username": "kimichen", "nick_name": "Kimi Chen"}],
            )
            cache = FakeCache(db_path)

            first_dir = os.path.join(tmpdir, "kimichen_046c", "db_storage")
            second_dir = os.path.join(tmpdir, "other_1234", "db_storage")

            self.assertEqual(
                contacts.get_self_username(first_dir, cache, os.path.join(tmpdir, "missing")),
                "kimichen",
            )
            self.assertEqual(
                contacts.get_self_username(second_dir, cache, os.path.join(tmpdir, "missing")),
                "",
            )

    def test_search_contacts_filters_by_query_and_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "contact", "contact.db")
            _create_contact_db(
                db_path,
                [
                    {"username": "alice", "nick_name": "Alice"},
                    {"username": "bob", "nick_name": "Bob", "remark": "Builder"},
                    {"username": "carol", "nick_name": "Carol"},
                ],
            )
            cache = FakeCache(db_path)

            result = contacts.search_contacts(
                cache,
                os.path.join(tmpdir, "missing"),
                query="b",
                limit=1,
            )

        self.assertEqual(result, [{"username": "bob", "nick_name": "Bob", "remark": "Builder"}])


if __name__ == "__main__":
    unittest.main()
