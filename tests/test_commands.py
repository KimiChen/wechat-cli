import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from click.testing import CliRunner

from wechat_cli.commands import contacts as contacts_cmd
from wechat_cli.commands import export as export_cmd
from wechat_cli.commands import favorites as favorites_cmd
from wechat_cli.commands import history as history_cmd
from wechat_cli.commands import init as init_cmd
from wechat_cli.commands import members as members_cmd
from wechat_cli.commands import search as search_cmd
from wechat_cli.commands import session_updates as session_updates_cmd
from wechat_cli.commands import sessions as sessions_cmd
from wechat_cli.commands import stats as stats_cmd
from wechat_cli.commands import unread as unread_cmd


class CommandRegressionTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.app = SimpleNamespace(
            cache=object(),
            decrypted_dir="ignored",
            msg_db_keys=[],
            db_dir="ignored",
            display_name_fn=lambda username, names: names.get(username, username),
        )

    def test_members_text_mode_lists_all_members(self):
        members = [
            {"display_name": "Alice", "username": "alice", "remark": ""},
            {"display_name": "Bob", "username": "bob", "remark": "Teammate"},
        ]
        with mock.patch.object(members_cmd, "resolve_username", return_value="room@chatroom"):
            with mock.patch.object(members_cmd, "get_contact_names", return_value={"room@chatroom": "Team"}):
                with mock.patch.object(members_cmd, "get_group_members", return_value={"members": members, "owner": "Alice"}):
                    result = self.runner.invoke(members_cmd.members, ["Team", "--format", "text"], obj=self.app)

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Alice  (alice)", result.output)
        self.assertIn("Bob  (bob)  备注: Teammate", result.output)

    def test_search_reports_missing_message_tables(self):
        resolved = [
            {
                "display_name": "Known",
                "username": "known",
                "db_path": "known.db",
                "table_name": "Msg_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "message_tables": [{"db_path": "known.db", "table_name": "Msg_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}],
                "is_group": False,
                "query": "Known",
            }
        ]

        with mock.patch.object(search_cmd, "validate_pagination", return_value=None):
            with mock.patch.object(search_cmd, "parse_time_range", return_value=(None, None)):
                with mock.patch.object(search_cmd, "get_contact_names", return_value={}):
                    with mock.patch.object(
                        search_cmd,
                        "resolve_chat_contexts",
                        return_value=(resolved, [], ["NoHistory"]),
                    ):
                        with mock.patch.object(
                            search_cmd,
                            "collect_chat_search",
                            return_value=([(1, "[Known] hello")], []),
                        ):
                            result = self.runner.invoke(
                                search_cmd.search,
                                ["hello", "--chat", "Known", "--chat", "NoHistory", "--format", "json"],
                                obj=self.app,
                            )

        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["results"], ["[Known] hello"])
        self.assertEqual(payload["failures"], ["无消息记录: NoHistory"])

    def test_sessions_json_uses_standard_result_shape(self):
        rows = [
            ("alice", 1, "hello", 1_700_000_000, 1, "", ""),
        ]
        with mock.patch.object(sessions_cmd, "query_session_rows", return_value=rows):
            with mock.patch.object(sessions_cmd, "get_contact_names", return_value={"alice": "Alice"}):
                result = self.runner.invoke(
                    sessions_cmd.sessions,
                    ["--limit", "1", "--format", "json"],
                    obj=self.app,
                )

        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["scope"], "最近会话")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["offset"], 0)
        self.assertEqual(payload["limit"], 1)
        self.assertIsNone(payload["failures"])
        self.assertEqual(len(payload["sessions"]), 1)
        self.assertEqual(payload["sessions"][0]["chat"], "Alice")

    def test_contacts_json_uses_standard_result_shape(self):
        contacts = [{"username": "alice", "nick_name": "Alice", "remark": ""}]
        with mock.patch.object(contacts_cmd, "search_contacts", return_value=contacts):
            result = self.runner.invoke(
                contacts_cmd.contacts,
                ["--query", "ali", "--limit", "1", "--format", "json"],
                obj=self.app,
            )

        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["scope"], "联系人搜索: ali")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["offset"], 0)
        self.assertEqual(payload["limit"], 1)
        self.assertEqual(payload["query"], "ali")
        self.assertIsNone(payload["failures"])
        self.assertEqual(payload["contacts"], contacts)

    def test_favorites_json_uses_standard_result_shape(self):
        favorites = [{"id": 1, "summary": "hello"}]
        with mock.patch.object(favorites_cmd, "get_contact_names", return_value={}):
            with mock.patch.object(favorites_cmd, "list_favorites", return_value=favorites):
                result = self.runner.invoke(
                    favorites_cmd.favorites,
                    ["--type", "text", "--limit", "2", "--format", "json"],
                    obj=self.app,
                )

        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["scope"], "收藏")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["offset"], 0)
        self.assertEqual(payload["limit"], 2)
        self.assertEqual(payload["type"], "text")
        self.assertIsNone(payload["failures"])
        self.assertEqual(payload["favorites"], favorites)

    def test_stats_json_uses_standard_result_shape(self):
        chat_ctx = {
            "display_name": "Team",
            "username": "room@chatroom",
            "is_group": True,
            "db_path": "team.db",
            "table_name": "Msg_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "message_tables": [{"db_path": "team.db", "table_name": "Msg_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}],
            "query": "Team",
        }
        stats_result = {
            "total": 12,
            "type_breakdown": {"文本": 10, "图片": 2},
            "top_senders": [{"name": "Alice", "count": 5}],
            "hourly": {hour: 0 for hour in range(24)},
            "failures": ["partial"],
        }

        with mock.patch.object(stats_cmd, "parse_time_range", return_value=(None, None)):
            with mock.patch.object(stats_cmd, "resolve_chat_context", return_value=chat_ctx):
                with mock.patch.object(stats_cmd, "get_contact_names", return_value={}):
                    with mock.patch.object(stats_cmd, "collect_chat_stats", return_value=stats_result):
                        result = self.runner.invoke(
                            stats_cmd.stats,
                            ["Team", "--format", "json"],
                            obj=self.app,
                        )

        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["scope"], "Team")
        self.assertEqual(payload["count"], 12)
        self.assertEqual(payload["chat"], "Team")
        self.assertTrue(payload["is_group"])
        self.assertEqual(payload["failures"], ["partial"])
        self.assertEqual(payload["total"], 12)

    def test_session_updates_command_outputs_service_payload_as_json(self):
        payload = {
            "scope": "会话更新",
            "count": 1,
            "failures": None,
            "first_call": True,
            "unread_count": 1,
            "stream_type": "session_updates",
            "tracked_by": "session_last_timestamp",
            "snapshot_kind": "initial_unread_sessions",
            "messages": [{"chat": "Team"}],
        }
        with mock.patch.object(session_updates_cmd, "collect_session_updates", return_value=payload):
            result = self.runner.invoke(
                session_updates_cmd.session_updates,
                ["--format", "json"],
                obj=self.app,
            )

        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["scope"], "会话更新")
        self.assertEqual(payload["stream_type"], "session_updates")
        self.assertEqual(payload["tracked_by"], "session_last_timestamp")
        self.assertEqual(payload["snapshot_kind"], "initial_unread_sessions")
        self.assertTrue(payload["first_call"])
        self.assertEqual(payload["unread_count"], 1)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["messages"][0]["chat"], "Team")

    def test_new_messages_alias_uses_same_service_payload(self):
        payload = {
            "scope": "会话更新",
            "count": 1,
            "failures": None,
            "first_call": False,
            "new_count": 1,
            "stream_type": "session_updates",
            "tracked_by": "session_last_timestamp",
            "snapshot_kind": "changed_sessions_since_last_check",
            "messages": [{"chat": "Alice"}],
        }
        with mock.patch.object(session_updates_cmd, "collect_session_updates", return_value=payload):
            result = self.runner.invoke(
                session_updates_cmd.new_messages,
                ["--format", "json"],
                obj=self.app,
            )

        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["scope"], "会话更新")
        self.assertFalse(payload["first_call"])
        self.assertEqual(payload["snapshot_kind"], "changed_sessions_since_last_check")
        self.assertEqual(payload["new_count"], 1)
        self.assertEqual(payload["messages"][0]["chat"], "Alice")

    def test_history_json_uses_standard_result_shape(self):
        chat_ctx = {
            "display_name": "Team",
            "username": "room@chatroom",
            "is_group": True,
            "db_path": "team.db",
            "table_name": "Msg_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "message_tables": [{"db_path": "team.db", "table_name": "Msg_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}],
            "query": "Team",
        }
        with mock.patch.object(history_cmd, "validate_pagination", return_value=None):
            with mock.patch.object(history_cmd, "parse_time_range", return_value=(100, 200)):
                with mock.patch.object(history_cmd, "resolve_chat_context", return_value=chat_ctx):
                    with mock.patch.object(history_cmd, "get_contact_names", return_value={}):
                        with mock.patch.object(
                            history_cmd,
                            "collect_chat_history",
                            return_value=(["[Team] hello"], ["partial"]),
                        ):
                            result = self.runner.invoke(
                                history_cmd.history,
                                [
                                    "Team",
                                    "--limit",
                                    "5",
                                    "--offset",
                                    "2",
                                    "--start-time",
                                    "2026-04-01",
                                    "--end-time",
                                    "2026-04-02",
                                    "--format",
                                    "json",
                                ],
                                obj=self.app,
                            )

        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["offset"], 2)
        self.assertEqual(payload["limit"], 5)
        self.assertEqual(payload["chat"], "Team")
        self.assertEqual(payload["username"], "room@chatroom")
        self.assertTrue(payload["is_group"])
        self.assertEqual(payload["start_time"], "2026-04-01")
        self.assertEqual(payload["end_time"], "2026-04-02")
        self.assertEqual(payload["failures"], ["partial"])
        self.assertEqual(payload["messages"], ["[Team] hello"])

    def test_unread_json_uses_standard_result_shape(self):
        rows = [
            ("room@chatroom", 2, "hello", 1_700_000_000, 1, "alice", ""),
        ]
        with mock.patch.object(unread_cmd, "query_session_rows", return_value=rows):
            with mock.patch.object(
                unread_cmd,
                "get_contact_names",
                return_value={"room@chatroom": "Team", "alice": "Alice"},
            ):
                result = self.runner.invoke(
                    unread_cmd.unread,
                    ["--limit", "1", "--format", "json"],
                    obj=self.app,
                )

        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["offset"], 0)
        self.assertEqual(payload["limit"], 1)
        self.assertIsNone(payload["failures"])
        self.assertEqual(payload["sessions"][0]["chat"], "Team")
        self.assertEqual(payload["sessions"][0]["unread"], 2)

    def test_unread_reports_session_db_errors_with_exit_code_3(self):
        with mock.patch.object(
            unread_cmd,
            "query_session_rows",
            side_effect=unread_cmd.SessionDBError("session.db missing"),
        ):
            result = self.runner.invoke(
                unread_cmd.unread,
                ["--format", "text"],
                obj=self.app,
            )

        self.assertEqual(result.exit_code, 3, result.output)
        self.assertIn("session.db missing", result.output)

    def test_export_writes_requested_output_file(self):
        chat_ctx = {
            "display_name": "Team",
            "username": "room@chatroom",
            "is_group": True,
            "db_path": "team.db",
        }
        with self.runner.isolated_filesystem():
            with mock.patch.object(export_cmd, "validate_pagination", return_value=None):
                with mock.patch.object(export_cmd, "parse_time_range", return_value=(None, None)):
                    with mock.patch.object(export_cmd, "resolve_chat_context", return_value=chat_ctx):
                        with mock.patch.object(export_cmd, "get_contact_names", return_value={}):
                            with mock.patch.object(
                                export_cmd,
                                "collect_chat_history",
                                return_value=(["[04-01 10:00] Alice: hello"], None),
                            ):
                                result = self.runner.invoke(
                                    export_cmd.export,
                                    ["Team", "--output", "chat.md"],
                                    obj=self.app,
                                )

            self.assertEqual(result.exit_code, 0, result.output)
            content = Path("chat.md").read_text(encoding="utf-8")
            self.assertIn("[04-01 10:00] Alice: hello", content)
            self.assertTrue(content.endswith("\n"))
            self.assertIn("chat.md", result.output)

    def test_init_reports_missing_auto_detected_db_dir(self):
        with self.runner.isolated_filesystem():
            state_dir = Path("state")
            config_file = state_dir / "config.json"
            keys_file = state_dir / "all_keys.json"

            with mock.patch.object(init_cmd, "STATE_DIR", str(state_dir)):
                with mock.patch.object(init_cmd, "CONFIG_FILE", str(config_file)):
                    with mock.patch.object(init_cmd, "KEYS_FILE", str(keys_file)):
                        with mock.patch.object(init_cmd, "auto_detect_db_dir", return_value=None):
                            result = self.runner.invoke(init_cmd.init, [])

        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("--db-dir", result.output)

    def test_init_skips_existing_state_without_force(self):
        with self.runner.isolated_filesystem():
            state_dir = Path("state")
            state_dir.mkdir()
            config_file = state_dir / "config.json"
            keys_file = state_dir / "all_keys.json"
            config_file.write_text("{}", encoding="utf-8")
            keys_file.write_text("{}", encoding="utf-8")

            with mock.patch.object(init_cmd, "STATE_DIR", str(state_dir)):
                with mock.patch.object(init_cmd, "CONFIG_FILE", str(config_file)):
                    with mock.patch.object(init_cmd, "KEYS_FILE", str(keys_file)):
                        result = self.runner.invoke(init_cmd.init, [])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("--force", result.output)


if __name__ == "__main__":
    unittest.main()
