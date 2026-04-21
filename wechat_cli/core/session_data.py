"""Helpers for querying and formatting session.db data."""

import os
import sqlite3
from contextlib import closing
from datetime import datetime

from .messages import decompress_content, format_msg_type

SESSION_DB_REL_PATH = os.path.join("session", "session.db")
_SESSION_BASE_QUERY = """
    SELECT username, unread_count, summary, last_timestamp,
           last_msg_type, last_msg_sender, last_sender_display_name
    FROM SessionTable
"""


class SessionDBError(RuntimeError):
    """Raised when session.db cannot be read."""


def get_session_db_path(cache):
    path = cache.get(SESSION_DB_REL_PATH)
    if not path:
        raise SessionDBError("无法解密 session.db")
    return path


def query_session_rows(cache, where_clause="last_timestamp > 0", params=(), limit=None):
    path = get_session_db_path(cache)
    sql = _SESSION_BASE_QUERY
    if where_clause:
        sql += f"\nWHERE {where_clause}"
    sql += "\nORDER BY last_timestamp DESC"

    query_params = list(params)
    if limit is not None:
        sql += "\nLIMIT ?"
        query_params.append(limit)

    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(sql, tuple(query_params)).fetchall()


def normalize_session_summary(summary):
    if isinstance(summary, bytes):
        summary = decompress_content(summary, 4) or "(压缩内容)"
    if isinstance(summary, str) and ":\n" in summary:
        summary = summary.split(":\n", 1)[1]
    return str(summary or "")


def session_row_to_state(row):
    username, unread, summary, timestamp, msg_type, sender, sender_name = row
    return username, {
        "unread": unread or 0,
        "summary": summary,
        "timestamp": timestamp,
        "msg_type": msg_type,
        "sender": sender or "",
        "sender_name": sender_name or "",
    }


def rows_to_state_map(rows):
    return dict(session_row_to_state(row) for row in rows)


def session_state_to_entry(username, state, names, time_format="%m-%d %H:%M"):
    display = names.get(username, username)
    is_group = "@chatroom" in username

    sender_display = ""
    if is_group and state["sender"]:
        sender_display = names.get(state["sender"], state["sender_name"] or state["sender"])

    return {
        "chat": display,
        "username": username,
        "is_group": is_group,
        "unread": state["unread"],
        "last_message": normalize_session_summary(state["summary"]),
        "msg_type": format_msg_type(state["msg_type"]),
        "sender": sender_display,
        "timestamp": state["timestamp"],
        "time": datetime.fromtimestamp(state["timestamp"]).strftime(time_format),
    }


def session_row_to_entry(row, names, time_format="%m-%d %H:%M"):
    username, state = session_row_to_state(row)
    return session_state_to_entry(username, state, names, time_format=time_format)
