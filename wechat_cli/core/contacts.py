"""Contact lookup helpers."""

import os
import re
import sqlite3


def _get_state(cache):
    state = getattr(cache, "_contacts_state", None)
    if state is None:
        state = {
            "datasets": {},
            "self_usernames": {},
        }
        setattr(cache, "_contacts_state", state)
    return state


def _get_dataset_state(cache, decrypted_dir):
    state = _get_state(cache)
    key = os.path.abspath(decrypted_dir or "")
    return state["datasets"].setdefault(
        key,
        {
            "names": None,
            "full": None,
        },
    )


def _load_contacts_from(db_path):
    names = {}
    full = []
    conn = sqlite3.connect(db_path)
    try:
        for username, nick_name, remark in conn.execute(
            "SELECT username, nick_name, remark FROM contact"
        ).fetchall():
            display = remark if remark else nick_name if nick_name else username
            names[username] = display
            full.append(
                {
                    "username": username,
                    "nick_name": nick_name or "",
                    "remark": remark or "",
                }
            )
    finally:
        conn.close()
    return names, full


def _resolve_contact_db_path(cache, decrypted_dir):
    pre_decrypted = os.path.join(decrypted_dir, "contact", "contact.db")
    if os.path.exists(pre_decrypted):
        return pre_decrypted
    return cache.get(os.path.join("contact", "contact.db"))


def _load_contact_dataset(cache, decrypted_dir):
    dataset = _get_dataset_state(cache, decrypted_dir)
    if dataset["names"] is not None:
        return dataset["names"], dataset["full"]

    db_path = _resolve_contact_db_path(cache, decrypted_dir)
    if not db_path:
        dataset["names"] = {}
        dataset["full"] = []
        return dataset["names"], dataset["full"]

    try:
        dataset["names"], dataset["full"] = _load_contacts_from(db_path)
    except Exception:
        dataset["names"] = {}
        dataset["full"] = []
    return dataset["names"], dataset["full"]


def get_contact_names(cache, decrypted_dir):
    names, _ = _load_contact_dataset(cache, decrypted_dir)
    return names


def get_contact_full(cache, decrypted_dir):
    _, full = _load_contact_dataset(cache, decrypted_dir)
    return full


def resolve_username(chat_name, cache, decrypted_dir):
    names = get_contact_names(cache, decrypted_dir)
    if chat_name in names or chat_name.startswith("wxid_") or "@chatroom" in chat_name:
        return chat_name

    chat_lower = chat_name.lower()
    for username, display in names.items():
        if chat_lower == display.lower():
            return username
    for username, display in names.items():
        if chat_lower in display.lower():
            return username
    return None


def get_self_username(db_dir, cache, decrypted_dir):
    if not db_dir:
        return ""

    state = _get_state(cache)
    key = os.path.abspath(db_dir)
    if key in state["self_usernames"]:
        return state["self_usernames"][key]

    names = get_contact_names(cache, decrypted_dir)
    account_dir = os.path.basename(os.path.dirname(db_dir))
    candidates = [account_dir]
    match = re.fullmatch(r"(.+)_([0-9a-fA-F]{4,})", account_dir)
    if match:
        candidates.insert(0, match.group(1))

    resolved = ""
    for candidate in candidates:
        if candidate and candidate in names:
            resolved = candidate
            break

    state["self_usernames"][key] = resolved
    return resolved


def get_group_members(chatroom_username, cache, decrypted_dir):
    """Return group members and owner info."""
    db_path = _resolve_contact_db_path(cache, decrypted_dir)
    if not db_path:
        return {"members": [], "owner": ""}

    names = get_contact_names(cache, decrypted_dir)
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM contact WHERE username = ?",
            (chatroom_username,),
        ).fetchone()
        if not row:
            return {"members": [], "owner": ""}
        room_id = row[0]

        owner = ""
        owner_row = conn.execute(
            "SELECT owner FROM chat_room WHERE id = ?",
            (room_id,),
        ).fetchone()
        if owner_row and owner_row[0]:
            owner = names.get(owner_row[0], owner_row[0])

        member_ids = [
            item[0]
            for item in conn.execute(
                "SELECT member_id FROM chatroom_member WHERE room_id = ?",
                (room_id,),
            ).fetchall()
        ]
        if not member_ids:
            return {"members": [], "owner": owner}

        placeholders = ",".join("?" * len(member_ids))
        members = []
        for _, username, nick_name, remark in conn.execute(
            f"SELECT id, username, nick_name, remark FROM contact WHERE id IN ({placeholders})",
            member_ids,
        ):
            display = remark if remark else nick_name if nick_name else username
            members.append(
                {
                    "username": username,
                    "nick_name": nick_name or "",
                    "remark": remark or "",
                    "display_name": display,
                }
            )

        owner_username = owner_row[0] if owner_row else ""
        members.sort(
            key=lambda item: (
                0 if item["username"] == owner_username else 1,
                item["display_name"],
            )
        )
        return {"members": members, "owner": owner}
    finally:
        conn.close()


def get_contact_detail(username, cache, decrypted_dir):
    db_path = _resolve_contact_db_path(cache, decrypted_dir)
    if not db_path:
        return None

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT username, nick_name, remark, alias, description, "
            "small_head_url, big_head_url, verify_flag, local_type "
            "FROM contact WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            return None
        (
            resolved_username,
            nick_name,
            remark,
            alias,
            description,
            small_head_url,
            big_head_url,
            verify_flag,
            local_type,
        ) = row
        return {
            "username": resolved_username,
            "nick_name": nick_name or "",
            "remark": remark or "",
            "alias": alias or "",
            "description": description or "",
            "avatar": small_head_url or big_head_url or "",
            "verify_flag": verify_flag or 0,
            "local_type": local_type,
            "is_group": "@chatroom" in resolved_username,
            "is_subscription": resolved_username.startswith("gh_"),
        }
    finally:
        conn.close()


def display_name_for_username(username, names, db_dir, cache, decrypted_dir):
    if not username:
        return ""
    if username == get_self_username(db_dir, cache, decrypted_dir):
        return "me"
    return names.get(username, username)
