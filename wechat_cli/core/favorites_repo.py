"""Repository helpers for reading favorite.db."""

import os
import sqlite3
from contextlib import closing


FAVORITE_DB_REL_PATH = os.path.join("favorite", "favorite.db")


def resolve_favorite_db_path(cache, decrypted_dir):
    pre_decrypted = os.path.join(decrypted_dir, "favorite", "favorite.db")
    if os.path.exists(pre_decrypted):
        return pre_decrypted
    return cache.get(FAVORITE_DB_REL_PATH)


def query_favorite_rows(db_path, limit=20, favorite_type=None, keyword=None):
    where_parts = []
    params = []

    if favorite_type is not None:
        where_parts.append("type = ?")
        params.append(favorite_type)

    if keyword:
        where_parts.append("content LIKE ?")
        params.append(f"%{keyword}%")

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute(
            f"""
            SELECT local_id, type, update_time, content, fromusr, realchatname
            FROM fav_db_item
            {where_sql}
            ORDER BY update_time DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
