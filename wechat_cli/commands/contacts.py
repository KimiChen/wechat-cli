"""contacts 命令 — 搜索或查看联系人"""

import click

from ..core.contacts import find_contact_detail, search_contacts
from ..output.formatter import output


@click.command("contacts")
@click.option("--query", default="", help="搜索关键词（匹配昵称、备注、wxid）")
@click.option("--detail", default=None, help="查看联系人详情（传入昵称/备注/wxid）")
@click.option("--limit", default=50, help="返回数量")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="输出格式")
@click.pass_context
def contacts(ctx, query, detail, limit, fmt):
    """搜索或列出联系人

    \b
    示例:
      wechat-cli contacts --query "李"              # 搜索联系人
      wechat-cli contacts --detail "张三"          # 查看联系人详情
      wechat-cli contacts --detail "wxid_xxx"       # 通过 wxid 查看
    """
    app = ctx.obj

    if detail:
        _show_detail(app, detail, fmt)
        return

    matched = search_contacts(
        app.cache,
        app.decrypted_dir,
        query=query,
        limit=limit,
    )

    if fmt == 'json':
        output(matched, 'json')
    else:
        header = f"找到 {len(matched)} 个联系人:"
        lines = []
        for c in matched:
            display = c['remark'] or c['nick_name'] or c['username']
            line = f"{display}  ({c['username']})"
            if c['remark']:
                line += f"  备注: {c['remark']}"
            lines.append(line)
        output(header + "\n\n" + "\n".join(lines), 'text')


def _show_detail(app, name_or_id, fmt):
    """显示联系人详情。"""
    info = find_contact_detail(name_or_id, app.cache, app.decrypted_dir)
    if not info:
        click.echo(f"找不到联系人: {name_or_id}", err=True)
        return

    if fmt == 'json':
        output(info, 'json')
    else:
        lines = [f"联系人详情: {info['nick_name']}"]
        if info['remark']:
            lines.append(f"备注: {info['remark']}")
        if info['alias']:
            lines.append(f"微信号: {info['alias']}")
        lines.append(f"wxid: {info['username']}")
        if info['description']:
            lines.append(f"个性签名: {info['description']}")
        if info['is_group']:
            lines.append("类型: 群聊")
        elif info['is_subscription']:
            lines.append("类型: 公众号")
        elif info['verify_flag'] and info['verify_flag'] >= 8:
            lines.append("类型: 企业认证")
        if info['avatar']:
            lines.append(f"头像: {info['avatar']}")
        output("\n".join(lines), 'text')
