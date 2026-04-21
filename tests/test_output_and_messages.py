import io
import hashlib
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from unittest import mock

from wechat_cli.core import messages
from wechat_cli.core import messages_repo
from wechat_cli.output import formatter


class FailingStream:
    def __init__(self):
        self.encoding = "gbk"
        self.buffer = io.BytesIO()
        self.flushed = False

    def write(self, text):
        raise UnicodeEncodeError("gbk", text, 0, 1, "boom")

    def flush(self):
        self.flushed = True


class FakeMessageCache:
    def __init__(self, mapping):
        self.mapping = mapping
        self.version_tokens = {
            rel_key: (index, 0)
            for index, rel_key in enumerate(mapping, start=1)
        }

    def get(self, rel_key):
        return self.mapping.get(rel_key)

    def describe(self, rel_key):
        path = self.get(rel_key)
        if not path:
            return None
        version_token = self.version_tokens[rel_key]
        return {
            "path": path,
            "db_mtime": version_token[0],
            "wal_mtime": version_token[1],
            "version_token": version_token,
        }


def _message_table_name(username):
    return f"Msg_{hashlib.md5(username.encode()).hexdigest()}"


def _create_message_db(path, rows_by_user):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE Name2Id (user_name TEXT)")
        sender_ids = {}
        for username in rows_by_user:
            cursor = conn.execute(
                "INSERT INTO Name2Id (user_name) VALUES (?)",
                (username,),
            )
            sender_ids[username] = cursor.lastrowid

        for username, rows in rows_by_user.items():
            table_name = _message_table_name(username)
            conn.execute(
                f"CREATE TABLE [{table_name}] ("
                "local_id INTEGER, "
                "local_type INTEGER, "
                "create_time INTEGER, "
                "real_sender_id INTEGER, "
                "message_content TEXT, "
                "WCDB_CT_message_content INTEGER)"
            )
            for index, row in enumerate(rows, start=1):
                conn.execute(
                    f"INSERT INTO [{table_name}] "
                    "(local_id, local_type, create_time, real_sender_id, message_content, WCDB_CT_message_content) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        index,
                        row.get("local_type", 1),
                        row.get("create_time", 0),
                        sender_ids[username],
                        row.get("message_content", ""),
                        row.get("content_type", 0),
                    ),
                )
        conn.commit()
    finally:
        conn.close()


def _append_message_table(path, username, rows):
    conn = sqlite3.connect(path)
    try:
        cursor = conn.execute(
            "INSERT INTO Name2Id (user_name) VALUES (?)",
            (username,),
        )
        sender_id = cursor.lastrowid
        table_name = _message_table_name(username)
        conn.execute(
            f"CREATE TABLE [{table_name}] ("
            "local_id INTEGER, "
            "local_type INTEGER, "
            "create_time INTEGER, "
            "real_sender_id INTEGER, "
            "message_content TEXT, "
            "WCDB_CT_message_content INTEGER)"
        )
        for index, row in enumerate(rows, start=1):
            conn.execute(
                f"INSERT INTO [{table_name}] "
                "(local_id, local_type, create_time, real_sender_id, message_content, WCDB_CT_message_content) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    index,
                    row.get("local_type", 1),
                    row.get("create_time", 0),
                    sender_id,
                    row.get("message_content", ""),
                    row.get("content_type", 0),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _create_media_layout(tmpdir):
    account_dir = os.path.join(tmpdir, "account")
    db_dir = os.path.join(account_dir, "db_storage")
    msg_dir = os.path.join(account_dir, "msg")
    os.makedirs(db_dir, exist_ok=True)
    os.makedirs(msg_dir, exist_ok=True)
    return db_dir, msg_dir


def _media_timestamp():
    return int(datetime(2026, 4, 21, 12, 0, 0).timestamp())


class OutputAndMessagesTests(unittest.TestCase):
    def test_output_text_falls_back_after_unicode_encode_error(self):
        stream = FailingStream()
        formatter.output_text("hello 😊", stream)
        self.assertTrue(stream.flushed)
        self.assertNotEqual(stream.buffer.getvalue(), b"")

    def test_reply_message_uses_ascii_arrow(self):
        content = (
            "<msg><appmsg><title>Reply</title><type>57</type>"
            "<refermsg><displayname>Alice</displayname><content>Hello</content></refermsg>"
            "</appmsg></msg>"
        )
        text = messages._format_app_message_text(
            content,
            49,
            False,
            "chat",
            "Chat",
            {},
            lambda username, names: username,
        )
        self.assertIn("-> 回复 Alice: Hello", text)
        self.assertNotIn("↳", text)

    def test_collect_chat_stats_reports_failures(self):
        ctx = {
            "query": "Chat",
            "username": "chat",
            "display_name": "Chat",
            "db_path": "unused",
            "table_name": "Msg_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "is_group": False,
        }
        broken_ctx = {
            "query": "Chat",
            "username": "chat",
            "display_name": "Chat",
            "db_path": "Z:/definitely/missing/path/message.db",
            "table_name": "Msg_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "is_group": False,
        }
        with mock.patch.object(messages, "_iter_table_contexts", return_value=[broken_ctx]):
            result = messages.collect_chat_stats(ctx, {}, lambda username, names: username)
        self.assertIsNotNone(result["failures"])
        self.assertEqual(len(result["failures"]), 1)
        self.assertIn("Chat:", result["failures"][0])

    def test_resolve_chat_contexts_reuses_message_db_discovery_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rel_keys = [
                os.path.join("message", "message_1.db"),
                os.path.join("message", "message_2.db"),
            ]
            db1 = os.path.join(tmpdir, "message_1.db")
            db2 = os.path.join(tmpdir, "message_2.db")
            _create_message_db(
                db1,
                {
                    "alice": [{"create_time": 10, "message_content": "hello alice"}],
                    "bob": [{"create_time": 20, "message_content": "hello bob"}],
                },
            )
            _create_message_db(
                db2,
                {"carol": [{"create_time": 30, "message_content": "hello carol"}]},
            )
            cache = FakeMessageCache({rel_keys[0]: db1, rel_keys[1]: db2})
            names = {"alice": "Alice", "bob": "Bob", "carol": "Carol"}

            with mock.patch(
                "wechat_cli.core.contacts.get_contact_names",
                return_value=names,
            ):
                with mock.patch.object(
                    messages_repo,
                    "load_message_db_index",
                    wraps=messages_repo.load_message_db_index,
                ) as load_index:
                    with mock.patch.object(
                        messages_repo,
                        "query_table_max_create_times",
                        wraps=messages_repo.query_table_max_create_times,
                    ) as load_max:
                        first = messages.resolve_chat_contexts(
                            ["Alice", "Bob", "Carol"],
                            rel_keys,
                            cache,
                            tmpdir,
                        )
                        second = messages.resolve_chat_contexts(
                            ["Alice", "Bob", "Carol"],
                            rel_keys,
                            cache,
                            tmpdir,
                        )

        self.assertEqual(first[1], [])
        self.assertEqual(first[2], [])
        self.assertEqual([ctx["display_name"] for ctx in first[0]], ["Alice", "Bob", "Carol"])
        self.assertEqual([ctx["display_name"] for ctx in second[0]], ["Alice", "Bob", "Carol"])
        self.assertEqual(load_index.call_count, 2)
        self.assertEqual(load_max.call_count, 2)

    def test_search_all_messages_reuses_cached_db_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rel_key = os.path.join("message", "message_1.db")
            db_path = os.path.join(tmpdir, "message_1.db")
            _create_message_db(
                db_path,
                {"alice": [{"create_time": 10, "message_content": "hello world"}]},
            )
            cache = FakeMessageCache({rel_key: db_path})
            names = {"alice": "Alice"}

            with mock.patch.object(
                messages_repo,
                "load_message_db_index",
                wraps=messages_repo.load_message_db_index,
            ) as load_index:
                first = messages.search_all_messages(
                    [rel_key],
                    cache,
                    names,
                    "hello",
                    lambda username, all_names: all_names.get(username, username),
                )
                second = messages.search_all_messages(
                    [rel_key],
                    cache,
                    names,
                    "hello",
                    lambda username, all_names: all_names.get(username, username),
                )

        self.assertEqual(load_index.call_count, 1)
        self.assertEqual(len(first[0]), 1)
        self.assertEqual(first[0], second[0])
        self.assertEqual(first[1], [])

    def test_resolve_chat_context_reloads_db_index_when_version_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rel_key = os.path.join("message", "message_1.db")
            db_path = os.path.join(tmpdir, "message_1.db")
            _create_message_db(
                db_path,
                {"alice": [{"create_time": 10, "message_content": "hello world"}]},
            )
            cache = FakeMessageCache({rel_key: db_path})
            names = {"alice": "Alice", "bob": "Bob"}

            with mock.patch.object(
                messages_repo,
                "load_message_db_index",
                wraps=messages_repo.load_message_db_index,
            ) as load_index:
                missing = messages.resolve_chat_context(
                    "bob",
                    [rel_key],
                    cache,
                    tmpdir,
                    names=names,
                )

                _append_message_table(
                    db_path,
                    "bob",
                    [{"create_time": 20, "message_content": "new hello"}],
                )
                cache.version_tokens[rel_key] = (99, 0)

                resolved = messages.resolve_chat_context(
                    "bob",
                    [rel_key],
                    cache,
                    tmpdir,
                    names=names,
                )

        self.assertEqual(missing["message_tables"], [])
        self.assertEqual(load_index.call_count, 2)
        self.assertEqual(resolved["display_name"], "Bob")
        self.assertEqual(len(resolved["message_tables"]), 1)
        self.assertEqual(
            resolved["message_tables"][0]["table_name"],
            _message_table_name("bob"),
        )

    def test_file_media_resolution_marks_fuzzy_filename_as_candidate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_dir, msg_dir = _create_media_layout(tmpdir)
            file_dir = os.path.join(msg_dir, "file", "2026-04")
            os.makedirs(file_dir, exist_ok=True)
            candidate_path = os.path.join(file_dir, "report-final.pdf")
            with open(candidate_path, "w", encoding="utf-8") as f:
                f.write("ok")

            content = (
                "<msg><appmsg><title>report.pdf</title><type>6</type></appmsg></msg>"
            )
            text = messages._format_app_message_text(
                content,
                49,
                False,
                "chat",
                "Chat",
                {},
                lambda username, names: username,
                resolve_media=True,
                db_dir=db_dir,
                create_time_ts=_media_timestamp(),
            )

        self.assertIn("[文件] report.pdf", text)
        self.assertIn("候选路径:", text)
        self.assertIn(candidate_path, text)
        self.assertIn("文件名启发式匹配", text)

    def test_image_media_resolution_returns_candidate_directory_not_random_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_dir, msg_dir = _create_media_layout(tmpdir)
            chat_username = "alice"
            attach_dir = os.path.join(
                msg_dir,
                "attach",
                hashlib.md5(chat_username.encode()).hexdigest(),
                "2026-04",
                "Img",
            )
            os.makedirs(attach_dir, exist_ok=True)
            for filename in ("a.dat", "b.dat"):
                with open(os.path.join(attach_dir, filename), "w", encoding="utf-8") as f:
                    f.write(filename)

            _, text = messages._format_message_text(
                7,
                3,
                "placeholder",
                False,
                chat_username,
                "Alice",
                {},
                lambda username, names: username,
                db_dir=db_dir,
                create_time_ts=_media_timestamp(),
                resolve_media=True,
            )

        self.assertIn("[图片] 候选目录:", text)
        self.assertIn(attach_dir, text)
        self.assertNotIn("a.dat", text)
        self.assertNotIn("b.dat", text)
        self.assertIn("未精确到当前文件", text)

    def test_video_media_resolution_marks_thumbnail_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_dir, msg_dir = _create_media_layout(tmpdir)
            video_dir = os.path.join(msg_dir, "video", "2026-04")
            os.makedirs(video_dir, exist_ok=True)
            thumb_path = os.path.join(video_dir, "clip_thumb.jpg")
            with open(thumb_path, "w", encoding="utf-8") as f:
                f.write("thumb")

            _, text = messages._format_message_text(
                9,
                43,
                "placeholder",
                False,
                "alice",
                "Alice",
                {},
                lambda username, names: username,
                db_dir=db_dir,
                create_time_ts=_media_timestamp(),
                resolve_media=True,
            )

        self.assertIn("[视频] 缩略图候选:", text)
        self.assertIn(thumb_path, text)
        self.assertIn("未定位到原视频", text)

    def test_image_media_resolution_reports_ambiguous_candidate_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_dir, msg_dir = _create_media_layout(tmpdir)
            first_dir = os.path.join(msg_dir, "attach", "hash_a", "2026-04", "Img")
            second_dir = os.path.join(msg_dir, "attach", "hash_b", "2026-04", "Img")
            os.makedirs(first_dir, exist_ok=True)
            os.makedirs(second_dir, exist_ok=True)

            _, text = messages._format_message_text(
                11,
                3,
                "placeholder",
                False,
                "",
                "",
                {},
                lambda username, names: username,
                db_dir=db_dir,
                create_time_ts=_media_timestamp(),
                resolve_media=True,
            )

        self.assertIn("未精确定位媒体文件", text)
        self.assertIn(first_dir, text)
        self.assertIn(second_dir, text)
        self.assertIn("同月份发现 2 个候选目录", text)


if __name__ == "__main__":
    unittest.main()
