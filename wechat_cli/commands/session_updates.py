"""session-updates command wrappers."""

import click

from ..core.session_data import SessionDBError
from ..core.session_updates import collect_session_updates, format_session_updates_text
from ..output.formatter import output


def _run_session_updates(ctx, fmt):
    app = ctx.obj

    try:
        result = collect_session_updates(app.cache, app.decrypted_dir)
    except SessionDBError as e:
        click.echo(f"错误: {e}", err=True)
        ctx.exit(3)

    if fmt == "json":
        output(result, "json")
        return

    output(format_session_updates_text(result), "text")


@click.command("session-updates")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="输出格式")
@click.pass_context
def session_updates(ctx, fmt):
    """获取自上次调用以来的会话更新（基于 session.db，不是逐条消息流）."""
    _run_session_updates(ctx, fmt)


@click.command("new-messages", hidden=True)
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="输出格式")
@click.pass_context
def new_messages(ctx, fmt):
    """兼容旧命令名，等同于 session-updates。"""
    _run_session_updates(ctx, fmt)
