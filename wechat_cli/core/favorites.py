"""Favorite query/formatting helpers."""

import xml.etree.ElementTree as ET
from datetime import datetime

from .favorites_repo import query_favorite_rows, resolve_favorite_db_path


FAVORITE_TYPE_LABELS = {
    1: "文本",
    2: "图片",
    5: "文章",
    19: "名片",
    20: "视频号",
}

FAVORITE_TYPE_FILTERS = {
    "text": 1,
    "image": 2,
    "article": 5,
    "card": 19,
    "video": 20,
}


class FavoriteDBError(RuntimeError):
    """Raised when favorite.db cannot be read."""


def parse_favorite_content(content, favorite_type):
    if not content:
        return ""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return ""
    item = root if root.tag == "favitem" else root.find(".//favitem")
    if item is None:
        return ""

    if favorite_type == 1:
        return (item.findtext("desc") or "").strip()
    if favorite_type == 2:
        return "[图片收藏]"
    if favorite_type == 5:
        title = (item.findtext(".//pagetitle") or "").strip()
        desc = (item.findtext(".//pagedesc") or "").strip()
        return f"{title} - {desc}" if desc else title
    if favorite_type == 19:
        return (item.findtext("desc") or "").strip()
    if favorite_type == 20:
        nickname = (item.findtext(".//nickname") or "").strip()
        desc = (item.findtext(".//desc") or "").strip()
        parts = [part for part in (nickname, desc) if part]
        return " ".join(parts) if parts else "[视频号]"
    desc = (item.findtext("desc") or "").strip()
    return desc if desc else "[收藏]"


def list_favorites(cache, decrypted_dir, names, limit=20, favorite_type=None, query=None):
    db_path = resolve_favorite_db_path(cache, decrypted_dir)
    if not db_path:
        raise FavoriteDBError("无法访问 favorite.db")

    type_code = FAVORITE_TYPE_FILTERS[favorite_type] if favorite_type else None
    rows = query_favorite_rows(
        db_path,
        limit=limit,
        favorite_type=type_code,
        keyword=query,
    )

    results = []
    for local_id, fav_type, ts, content, fromusr, realchat in rows:
        results.append(
            {
                "id": local_id,
                "type": FAVORITE_TYPE_LABELS.get(fav_type, f"type={fav_type}"),
                "time": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M"),
                "summary": parse_favorite_content(content, fav_type),
                "from": names.get(fromusr, fromusr) if fromusr else "",
                "source_chat": names.get(realchat, realchat) if realchat else "",
            }
        )
    return results
