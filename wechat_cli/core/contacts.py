"""Contact lookup helpers."""

import os
import re
import sqlite3

from . import contacts_repo


_CONTACT_DATASET_LOAD_ERRORS = (OSError, sqlite3.Error)


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
    for username, nick_name, remark in contacts_repo.query_contact_rows(db_path):
        display = remark if remark else nick_name if nick_name else username
        names[username] = display
        full.append(
            {
                "username": username,
                "nick_name": nick_name or "",
                "remark": remark or "",
            }
        )
    return names, full


def _resolve_contact_db_path(cache, decrypted_dir):
    return contacts_repo.resolve_contact_db_path(cache, decrypted_dir)


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
    except _CONTACT_DATASET_LOAD_ERRORS:
        dataset["names"] = {}
        dataset["full"] = []
    return dataset["names"], dataset["full"]


def get_contact_names(cache, decrypted_dir):
    names, _ = _load_contact_dataset(cache, decrypted_dir)
    return names


def get_contact_full(cache, decrypted_dir):
    _, full = _load_contact_dataset(cache, decrypted_dir)
    return full


def search_contacts(cache, decrypted_dir, query="", limit=None):
    full = get_contact_full(cache, decrypted_dir)
    if query:
        query_lower = query.lower()
        matched = [
            contact
            for contact in full
            if query_lower in contact.get("nick_name", "").lower()
            or query_lower in contact.get("remark", "").lower()
            or query_lower in contact.get("username", "").lower()
        ]
    else:
        matched = list(full)
    if limit is not None:
        matched = matched[:limit]
    return matched


def resolve_username_from_names(chat_name, names):
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


def resolve_username(chat_name, cache, decrypted_dir):
    names = get_contact_names(cache, decrypted_dir)
    return resolve_username_from_names(chat_name, names)


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
    group_data = contacts_repo.query_group_members(db_path, chatroom_username)
    if not group_data:
        return {"members": [], "owner": ""}

    owner_username = group_data["owner_username"]
    owner = names.get(owner_username, owner_username) if owner_username else ""

    members = []
    for _, username, nick_name, remark in group_data["members"]:
        display = remark if remark else nick_name if nick_name else username
        members.append(
            {
                "username": username,
                "nick_name": nick_name or "",
                "remark": remark or "",
                "display_name": display,
            }
        )

    members.sort(
        key=lambda item: (
            0 if item["username"] == owner_username else 1,
            item["display_name"],
        )
    )
    return {"members": members, "owner": owner}


def get_contact_detail(username, cache, decrypted_dir):
    db_path = _resolve_contact_db_path(cache, decrypted_dir)
    if not db_path:
        return None

    row = contacts_repo.query_contact_detail_row(db_path, username)
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


def find_contact_detail(name_or_id, cache, decrypted_dir):
    username = resolve_username(name_or_id, cache, decrypted_dir) or name_or_id
    return get_contact_detail(username, cache, decrypted_dir)


def display_name_for_username(username, names, db_dir, cache, decrypted_dir):
    if not username:
        return ""
    if username == get_self_username(db_dir, cache, decrypted_dir):
        return "me"
    return names.get(username, username)
