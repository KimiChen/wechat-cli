"""Session-level update tracking helpers."""

import json
import os

from .command_result import build_collection_result
from .config import STATE_DIR
from .contacts import get_contact_names
from .session_data import query_session_rows, rows_to_state_map, session_state_to_entry

STATE_FILE = os.path.join(STATE_DIR, "last_check.json")
STREAM_TYPE = "session_updates"
TRACKED_BY = "session_last_timestamp"
INITIAL_SNAPSHOT_KIND = "initial_unread_sessions"
CHANGED_SNAPSHOT_KIND = "changed_sessions_since_last_check"
SESSION_UPDATES_SCOPE = "会话更新"


def load_last_state(state_file=STATE_FILE):
    if not os.path.exists(state_file):
        return {}
    try:
        with open(state_file, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_last_state(state, state_file=STATE_FILE):
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f)


def timestamp_state(curr_state):
    return {username: state["timestamp"] for username, state in curr_state.items()}


def _build_initial_unread_snapshot(curr_state, names):
    messages = []
    for username, state in curr_state.items():
        if state["unread"] <= 0:
            continue
        entry = session_state_to_entry(username, state, names, time_format="%H:%M")
        messages.append(
            {
                "chat": entry["chat"],
                "username": entry["username"],
                "is_group": entry["is_group"],
                "unread": entry["unread"],
                "last_message": entry["last_message"],
                "msg_type": entry["msg_type"],
                "time": entry["time"],
                "timestamp": entry["timestamp"],
            }
        )
    return messages


def _build_changed_session_snapshot(curr_state, last_state, names):
    messages = []
    for username, state in curr_state.items():
        prev_ts = last_state.get(username, 0)
        if state["timestamp"] <= prev_ts:
            continue
        entry = session_state_to_entry(username, state, names, time_format="%H:%M:%S")
        messages.append(
            {
                "chat": entry["chat"],
                "username": entry["username"],
                "is_group": entry["is_group"],
                "last_message": entry["last_message"],
                "msg_type": entry["msg_type"],
                "sender": entry["sender"],
                "time": entry["time"],
                "timestamp": entry["timestamp"],
            }
        )
    messages.sort(key=lambda item: item["timestamp"])
    return messages


def collect_session_updates(cache, decrypted_dir, state_file=STATE_FILE):
    rows = query_session_rows(cache)
    names = get_contact_names(cache, decrypted_dir)
    curr_state = rows_to_state_map(rows)
    last_state = load_last_state(state_file)

    if not last_state:
        save_last_state(timestamp_state(curr_state), state_file)
        messages = _build_initial_unread_snapshot(curr_state, names)
        return build_collection_result(
            SESSION_UPDATES_SCOPE,
            "messages",
            messages,
            first_call=True,
            unread_count=len(messages),
            stream_type=STREAM_TYPE,
            tracked_by=TRACKED_BY,
            snapshot_kind=INITIAL_SNAPSHOT_KIND,
        )

    messages = _build_changed_session_snapshot(curr_state, last_state, names)
    save_last_state(timestamp_state(curr_state), state_file)
    return build_collection_result(
        SESSION_UPDATES_SCOPE,
        "messages",
        messages,
        first_call=False,
        new_count=len(messages),
        stream_type=STREAM_TYPE,
        tracked_by=TRACKED_BY,
        snapshot_kind=CHANGED_SNAPSHOT_KIND,
    )


def format_session_updates_text(result):
    messages = result["messages"]
    if result["first_call"]:
        if messages:
            lines = []
            for item in messages:
                tag = " [群]" if item["is_group"] else ""
                lines.append(
                    f"[{item['time']}] {item['chat']}{tag} ({item['unread']}条未读): {item['last_message']}"
                )
            return (
                "首次调用：已记录会话基线，并返回当前未读会话快照"
                "（基于 session.db，会话级更新，不是逐条消息流）\n\n"
                + "\n".join(lines)
            )
        return "首次调用：当前无未读会话，已记录会话基线（后续返回会话更新，不是逐条消息流）"

    if not messages:
        return "无会话更新（基于 session.db，会话级更新，不是逐条消息流）"

    lines = []
    for item in messages:
        entry = f"[{item['time']}] {item['chat']}"
        if item["is_group"]:
            entry += " [群]"
        entry += f": {item['msg_type']}"
        if item.get("sender"):
            entry += f" ({item['sender']})"
        entry += f" - {item['last_message']}"
        lines.append(entry)
    return (
        f"{len(messages)} 个会话更新（基于 session.db，会话级更新，不是逐条消息流）:\n\n"
        + "\n".join(lines)
    )
