"""Repository helpers for reading message_*.db files."""

import hashlib
import re
import sqlite3
from contextlib import closing

from .key_utils import key_path_variants


_MESSAGE_DB_RE = re.compile(r"message_\d+\.db$")
_MESSAGE_TABLE_RE = re.compile(r"Msg_[0-9a-f]{32}")


def find_msg_db_keys(all_keys):
    return sorted(
        [
            key
            for key in all_keys
            if any(variant.startswith("message/") for variant in key_path_variants(key))
            and any(_MESSAGE_DB_RE.search(variant) for variant in key_path_variants(key))
        ]
    )


def is_safe_msg_table_name(table_name):
    return bool(_MESSAGE_TABLE_RE.fullmatch(table_name))


def find_msg_tables_for_user(username, msg_db_keys, cache):
    table_name = f"Msg_{hashlib.md5(username.encode()).hexdigest()}"
    if not is_safe_msg_table_name(table_name):
        return []

    matches = []
    for rel_key in msg_db_keys:
        db_path = cache.get(rel_key)
        if not db_path:
            continue
        with closing(sqlite3.connect(db_path)) as conn:
            try:
                exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,),
                ).fetchone()
                if not exists:
                    continue
                max_create_time = conn.execute(
                    f"SELECT MAX(create_time) FROM [{table_name}]"
                ).fetchone()[0] or 0
                matches.append(
                    {
                        "db_path": db_path,
                        "table_name": table_name,
                        "max_create_time": max_create_time,
                    }
                )
            except Exception:
                continue

    matches.sort(key=lambda item: item["max_create_time"], reverse=True)
    return matches


def open_message_db(db_path):
    return closing(sqlite3.connect(db_path))


def load_name2id_map(conn):
    id_to_username = {}
    try:
        rows = conn.execute("SELECT rowid, user_name FROM Name2Id").fetchall()
    except sqlite3.Error:
        return id_to_username

    for rowid, user_name in rows:
        if user_name:
            id_to_username[rowid] = user_name
    return id_to_username


def build_message_filters(start_ts=None, end_ts=None, keyword="", msg_type_filter=None):
    clauses = []
    params = []
    if start_ts is not None:
        clauses.append("create_time >= ?")
        params.append(start_ts)
    if end_ts is not None:
        clauses.append("create_time <= ?")
        params.append(end_ts)
    if keyword:
        clauses.append("message_content LIKE ?")
        params.append(f"%{keyword}%")
    if msg_type_filter is not None:
        clauses.append("(local_type & 0xFFFFFFFF) = ?")
        params.append(msg_type_filter[0])
        if len(msg_type_filter) > 1:
            clauses.append("((local_type >> 32) & 0xFFFFFFFF) = ?")
            params.append(msg_type_filter[1])
    return clauses, params


def query_messages(conn, table_name, start_ts=None, end_ts=None, keyword="", limit=20, offset=0, msg_type_filter=None):
    if not is_safe_msg_table_name(table_name):
        raise ValueError(f"非法消息表名: {table_name}")

    clauses, params = build_message_filters(start_ts, end_ts, keyword, msg_type_filter)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT local_id, local_type, create_time, real_sender_id, message_content,
               WCDB_CT_message_content
        FROM [{table_name}]
        {where_sql}
        ORDER BY create_time DESC
    """
    if limit is None:
        return conn.execute(sql, params).fetchall()

    sql += "\n        LIMIT ? OFFSET ?"
    return conn.execute(sql, (*params, limit, offset)).fetchall()


def load_search_contexts_from_db(conn, db_path, names):
    table_rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'"
    ).fetchall()
    table_to_username = {}
    try:
        for (user_name,) in conn.execute("SELECT user_name FROM Name2Id").fetchall():
            if not user_name:
                continue
            table_name = f"Msg_{hashlib.md5(user_name.encode()).hexdigest()}"
            table_to_username[table_name] = user_name
    except sqlite3.Error:
        pass

    contexts = []
    for (table_name,) in table_rows:
        username = table_to_username.get(table_name, "")
        display_name = names.get(username, username) if username else table_name
        contexts.append(
            {
                "query": display_name,
                "username": username,
                "display_name": display_name,
                "db_path": db_path,
                "table_name": table_name,
                "is_group": "@chatroom" in username,
            }
        )
    return contexts


def _build_time_where(start_ts=None, end_ts=None):
    where_parts = []
    params = []
    if start_ts is not None:
        where_parts.append("create_time >= ?")
        params.append(start_ts)
    if end_ts is not None:
        where_parts.append("create_time <= ?")
        params.append(end_ts)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    return where_sql, params


def query_type_counts(conn, table_name, start_ts=None, end_ts=None):
    if not is_safe_msg_table_name(table_name):
        raise ValueError(f"非法消息表名: {table_name}")
    where_sql, params = _build_time_where(start_ts, end_ts)
    return conn.execute(
        f"SELECT (local_type & 0xFFFFFFFF), COUNT(*) FROM [{table_name}] {where_sql} GROUP BY (local_type & 0xFFFFFFFF)",
        params,
    ).fetchall()


def query_sender_counts(conn, table_name, start_ts=None, end_ts=None, limit=20):
    if not is_safe_msg_table_name(table_name):
        raise ValueError(f"非法消息表名: {table_name}")
    where_sql, params = _build_time_where(start_ts, end_ts)
    return conn.execute(
        f"SELECT real_sender_id, COUNT(*) FROM [{table_name}] {where_sql} GROUP BY real_sender_id ORDER BY COUNT(*) DESC LIMIT ?",
        (*params, limit),
    ).fetchall()


def query_hourly_counts(conn, table_name, start_ts=None, end_ts=None):
    if not is_safe_msg_table_name(table_name):
        raise ValueError(f"非法消息表名: {table_name}")
    where_sql, params = _build_time_where(start_ts, end_ts)
    return conn.execute(
        f"SELECT cast(strftime('%H', create_time, 'unixepoch', 'localtime') as integer), COUNT(*) "
        f"FROM [{table_name}] {where_sql} "
        "GROUP BY cast(strftime('%H', create_time, 'unixepoch', 'localtime') as integer)",
        params,
    ).fetchall()
