"""members command."""

import click

from ..core.command_result import build_collection_result
from ..core.contacts import get_contact_names, get_group_members, resolve_username
from ..output.formatter import output


@click.command("members")
@click.argument("group_name")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="输出格式")
@click.pass_context
def members(ctx, group_name, fmt):
    """查询群聊成员列表."""
    app = ctx.obj

    username = resolve_username(group_name, app.cache, app.decrypted_dir)
    if not username:
        click.echo(f"找不到: {group_name}", err=True)
        ctx.exit(1)

    if "@chatroom" not in username:
        click.echo(f"{group_name} 不是群聊", err=True)
        ctx.exit(1)

    names = get_contact_names(app.cache, app.decrypted_dir)
    display_name = names.get(username, username)
    result = get_group_members(username, app.cache, app.decrypted_dir)

    if fmt == "json":
        output(
            build_collection_result(
                display_name,
                "members",
                result["members"],
                group=display_name,
                username=username,
                owner=result["owner"],
                member_count=len(result["members"]),
            ),
            "json",
        )
        return

    lines = []
    for member in result["members"]:
        line = f"{member['display_name']}  ({member['username']})"
        if member["remark"]:
            line += f"  备注: {member['remark']}"
        lines.append(line)

    header = f"{display_name} 的群成员（共 {len(result['members'])} 人）"
    if result["owner"]:
        header += f"，群主: {result['owner']}"
    body = "\n".join(lines) if lines else "(无成员)"
    output(header + ":\n\n" + body, "text")
