"""new-messages command."""

import json
import os

import click

from ..core.config import STATE_DIR
from ..core.contacts import get_contact_names
from ..core.session_data import (
    SessionDBError,
    query_session_rows,
    rows_to_state_map,
    session_state_to_entry,
)
from ..output.formatter import output

STATE_FILE = os.path.join(STATE_DIR, "last_check.json")


def _load_last_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_last_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def _timestamp_state(curr_state):
    return {username: state["timestamp"] for username, state in curr_state.items()}


@click.command("new-messages")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="输出格式")
@click.pass_context
def new_messages(ctx, fmt):
    """获取自上次调用以来的新消息."""
    app = ctx.obj

    try:
        rows = query_session_rows(app.cache)
    except SessionDBError as e:
        click.echo(f"错误: {e}", err=True)
        ctx.exit(3)

    names = get_contact_names(app.cache, app.decrypted_dir)
    curr_state = rows_to_state_map(rows)
    last_state = _load_last_state()

    if not last_state:
        _save_last_state(_timestamp_state(curr_state))

        unread_msgs = []
        for username, state in curr_state.items():
            if state["unread"] <= 0:
                continue
            entry = session_state_to_entry(username, state, names, time_format="%H:%M")
            unread_msgs.append(
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

        if fmt == "json":
            output({"first_call": True, "unread_count": len(unread_msgs), "messages": unread_msgs}, "json")
            return

        if unread_msgs:
            lines = []
            for item in unread_msgs:
                tag = " [群]" if item["is_group"] else ""
                lines.append(f"[{item['time']}] {item['chat']}{tag} ({item['unread']}条未读): {item['last_message']}")
            output(f"当前 {len(unread_msgs)} 个未读会话\n\n" + "\n".join(lines), "text")
        else:
            output("当前无未读消息（已记录状态，下次调用将返回新消息）", "text")
        return

    new_msgs = []
    for username, state in curr_state.items():
        prev_ts = last_state.get(username, 0)
        if state["timestamp"] <= prev_ts:
            continue
        entry = session_state_to_entry(username, state, names, time_format="%H:%M:%S")
        new_msgs.append(
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

    _save_last_state(_timestamp_state(curr_state))
    new_msgs.sort(key=lambda item: item["timestamp"])

    if fmt == "json":
        output({"first_call": False, "new_count": len(new_msgs), "messages": new_msgs}, "json")
        return

    if not new_msgs:
        output("无新消息", "text")
        return

    lines = []
    for item in new_msgs:
        entry = f"[{item['time']}] {item['chat']}"
        if item["is_group"]:
            entry += " [群]"
        entry += f": {item['msg_type']}"
        if item["sender"]:
            entry += f" ({item['sender']})"
        entry += f" - {item['last_message']}"
        lines.append(entry)
    output(f"{len(new_msgs)} 条新消息:\n\n" + "\n".join(lines), "text")
