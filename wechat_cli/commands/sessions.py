"""sessions command."""

import click

from ..core.contacts import get_contact_names
from ..core.session_data import SessionDBError, query_session_rows, session_row_to_entry
from ..output.formatter import output


@click.command("sessions")
@click.option("--limit", default=20, help="返回的会话数量")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="输出格式")
@click.pass_context
def sessions(ctx, limit, fmt):
    """获取最近会话列表."""
    app = ctx.obj

    try:
        rows = query_session_rows(app.cache, limit=limit)
    except SessionDBError as e:
        click.echo(f"错误: {e}", err=True)
        ctx.exit(3)

    names = get_contact_names(app.cache, app.decrypted_dir)
    results = [session_row_to_entry(row, names) for row in rows]

    if fmt == "json":
        output(results, "json")
        return

    lines = []
    for item in results:
        entry = f"[{item['time']}] {item['chat']}"
        if item["is_group"]:
            entry += " [群]"
        if item["unread"] > 0:
            entry += f" ({item['unread']}条未读)"
        entry += f"\n  {item['msg_type']}: "
        if item["sender"]:
            entry += f"{item['sender']}: "
        entry += item["last_message"]
        lines.append(entry)
    output(f"最近 {len(results)} 个会话\n\n" + "\n\n".join(lines), "text")
