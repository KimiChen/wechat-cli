"""favorites 命令 — 查看微信收藏"""

import click

from ..core.command_result import build_collection_result
from ..core.contacts import get_contact_names
from ..core.favorites import (
    FAVORITE_TYPE_FILTERS,
    FavoriteDBError,
    list_favorites,
)
from ..output.formatter import output


@click.command("favorites")
@click.option("--limit", default=20, help="返回数量")
@click.option("--type", "fav_type", default=None,
              type=click.Choice(list(FAVORITE_TYPE_FILTERS.keys())),
              help="按类型过滤: text/image/article/card/video")
@click.option("--query", default=None, help="关键词搜索")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="输出格式")
@click.pass_context
def favorites(ctx, limit, fav_type, query, fmt):
    """查看微信收藏

    \b
    示例:
      wechat-cli favorites                        # 最近收藏
      wechat-cli favorites --type article         # 只看文章
      wechat-cli favorites --query "计算机网络"    # 搜索收藏
      wechat-cli favorites --limit 5 --format text
    """
    app = ctx.obj

    names = get_contact_names(app.cache, app.decrypted_dir)
    try:
        results = list_favorites(
            app.cache,
            app.decrypted_dir,
            names,
            limit=limit,
            favorite_type=fav_type,
            query=query,
        )
    except FavoriteDBError as e:
        click.echo(f"错误: {e}", err=True)
        ctx.exit(3)

    if fmt == 'json':
        output(
            build_collection_result(
                "收藏",
                "favorites",
                results,
                limit=limit,
                offset=0,
                type=fav_type or None,
                query=query or None,
            ),
            'json',
        )
    else:
        if not results:
            output("没有找到收藏", 'text')
            return
        lines = []
        for r in results:
            entry = f"[{r['time']}] [{r['type']}] {r['summary']}"
            if r['from']:
                entry += f"\n  来自: {r['from']}"
            if r['source_chat']:
                entry += f"  聊天: {r['source_chat']}"
            lines.append(entry)
        output(f"收藏列表（{len(results)} 条）:\n\n" + "\n\n".join(lines), 'text')
