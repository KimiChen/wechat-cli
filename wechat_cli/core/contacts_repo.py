"""Repository helpers for reading contact.db."""

import os
import sqlite3
from contextlib import closing


CONTACT_DB_REL_PATH = os.path.join("contact", "contact.db")


def resolve_contact_db_path(cache, decrypted_dir):
    pre_decrypted = os.path.join(decrypted_dir, "contact", "contact.db")
    if os.path.exists(pre_decrypted):
        return pre_decrypted
    return cache.get(CONTACT_DB_REL_PATH)


def query_contact_rows(db_path):
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute(
            "SELECT username, nick_name, remark FROM contact"
        ).fetchall()


def query_group_members(db_path, chatroom_username):
    with closing(sqlite3.connect(db_path)) as conn:
        room_row = conn.execute(
            "SELECT id FROM contact WHERE username = ?",
            (chatroom_username,),
        ).fetchone()
        if not room_row:
            return None

        room_id = room_row[0]
        owner_row = conn.execute(
            "SELECT owner FROM chat_room WHERE id = ?",
            (room_id,),
        ).fetchone()
        member_ids = [
            row[0]
            for row in conn.execute(
                "SELECT member_id FROM chatroom_member WHERE room_id = ?",
                (room_id,),
            ).fetchall()
        ]

        members = []
        if member_ids:
            placeholders = ",".join("?" * len(member_ids))
            members = conn.execute(
                f"SELECT id, username, nick_name, remark FROM contact WHERE id IN ({placeholders})",
                member_ids,
            ).fetchall()

        return {
            "owner_username": owner_row[0] if owner_row and owner_row[0] else "",
            "members": members,
        }


def query_contact_detail_row(db_path, username):
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute(
            "SELECT username, nick_name, remark, alias, description, "
            "small_head_url, big_head_url, verify_flag, local_type "
            "FROM contact WHERE username = ?",
            (username,),
        ).fetchone()
