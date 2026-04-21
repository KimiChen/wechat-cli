"""消息查询 — 分表查找、分页、格式化"""

import hashlib
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime

import zstandard as zstd

from . import messages_repo

_zstd_dctx = zstd.ZstdDecompressor()
_XML_UNSAFE_RE = re.compile(r'<!DOCTYPE|<!ENTITY', re.IGNORECASE)
_XML_PARSE_MAX_LEN = 20000
_QUERY_LIMIT_MAX = 500
_HISTORY_QUERY_BATCH_SIZE = 500

# 消息类型过滤映射: 名称 -> (base_type,) 或 (base_type, sub_type)
MSG_TYPE_FILTERS = {
    'text': (1,),
    'image': (3,),
    'voice': (34,),
    'video': (43,),
    'sticker': (47,),
    'location': (48,),
    'link': (49,),
    'file': (49, 6),
    'call': (50,),
    'system': (10000,),
}
MSG_TYPE_NAMES = list(MSG_TYPE_FILTERS.keys())


# ---- 消息 DB 发现 ----

def find_msg_db_keys(all_keys):
    return messages_repo.find_msg_db_keys(all_keys)


def _is_safe_msg_table_name(table_name):
    return messages_repo.is_safe_msg_table_name(table_name)


def _get_state(cache):
    state = getattr(cache, "_messages_state", None)
    if state is None:
        state = {"db_indexes": {}}
        setattr(cache, "_messages_state", state)
    return state


def _describe_cached_message_db(rel_key, cache):
    describe = getattr(cache, "describe", None)
    if callable(describe):
        info = describe(rel_key)
        if info:
            return info

    path = cache.get(rel_key)
    if not path:
        return None

    version_token = (path,)
    if os.path.exists(path):
        try:
            version_token = (os.path.getmtime(path), os.path.getsize(path))
        except OSError:
            pass
    return {
        "path": path,
        "db_mtime": None,
        "wal_mtime": None,
        "version_token": version_token,
    }


def _load_message_db_index(rel_key, cache):
    info = _describe_cached_message_db(rel_key, cache)
    if not info:
        return None

    state = _get_state(cache)
    cached = state["db_indexes"].get(rel_key)
    if (
        cached
        and cached["version_token"] == info["version_token"]
        and cached["db_path"] == info["path"]
    ):
        return cached

    with messages_repo.open_message_db(info["path"]) as conn:
        db_index = messages_repo.load_message_db_index(conn)

    cached = {
        "db_path": info["path"],
        "version_token": info["version_token"],
        "table_names": list(db_index["table_names"]),
        "table_name_set": set(db_index["table_name_set"]),
        "table_to_username": dict(db_index["table_to_username"]),
        "table_max_create_times": {},
    }
    state["db_indexes"][rel_key] = cached
    return cached


def _load_table_max_create_times(rel_key, cache, table_names):
    db_index = _load_message_db_index(rel_key, cache)
    if not db_index or not table_names:
        return {}

    missing = [
        table_name
        for table_name in table_names
        if table_name not in db_index["table_max_create_times"]
    ]
    if missing:
        with messages_repo.open_message_db(db_index["db_path"]) as conn:
            max_times = messages_repo.query_table_max_create_times(conn, missing)
        for table_name in missing:
            db_index["table_max_create_times"][table_name] = max_times.get(table_name, 0)

    return {
        table_name: db_index["table_max_create_times"].get(table_name, 0)
        for table_name in table_names
    }


def _build_search_contexts_from_index(db_index, names):
    contexts = []
    for table_name in db_index["table_names"]:
        username = db_index["table_to_username"].get(table_name, "")
        display_name = names.get(username, username) if username else table_name
        contexts.append(
            {
                "query": display_name,
                "username": username,
                "display_name": display_name,
                "db_path": db_index["db_path"],
                "table_name": table_name,
                "is_group": "@chatroom" in username,
            }
        )
    return contexts


def _find_msg_tables_for_users(usernames, msg_db_keys, cache):
    results = {username: [] for username in usernames if username}
    if not results:
        return results

    table_to_usernames = {}
    for username in results:
        table_name = f"Msg_{hashlib.md5(username.encode()).hexdigest()}"
        if not _is_safe_msg_table_name(table_name):
            continue
        table_to_usernames.setdefault(table_name, []).append(username)

    if not table_to_usernames:
        return results

    for rel_key in msg_db_keys:
        try:
            db_index = _load_message_db_index(rel_key, cache)
        except Exception:
            continue
        if not db_index:
            continue

        matching_tables = [
            table_name
            for table_name in db_index["table_names"]
            if table_name in table_to_usernames
        ]
        if not matching_tables:
            continue

        try:
            max_times = _load_table_max_create_times(rel_key, cache, matching_tables)
        except Exception:
            continue

        for table_name in matching_tables:
            for username in table_to_usernames[table_name]:
                results[username].append(
                    {
                        "db_path": db_index["db_path"],
                        "table_name": table_name,
                        "max_create_time": max_times.get(table_name, 0),
                    }
                )

    for username in results:
        results[username].sort(
            key=lambda item: item["max_create_time"],
            reverse=True,
        )
    return results


def _find_msg_tables_for_user(username, msg_db_keys, cache):
    return _find_msg_tables_for_users([username], msg_db_keys, cache).get(username, [])


# ---- 消息类型 ----

def _split_msg_type(t):
    try:
        t = int(t)
    except (TypeError, ValueError):
        return 0, 0
    if t > 0xFFFFFFFF:
        return t & 0xFFFFFFFF, t >> 32
    return t, 0


def format_msg_type(t):
    base_type, _ = _split_msg_type(t)
    return {
        1: '文本', 3: '图片', 34: '语音', 42: '名片',
        43: '视频', 47: '表情', 48: '位置', 49: '链接/文件',
        50: '通话', 10000: '系统', 10002: '撤回',
    }.get(base_type, f'type={t}')


# ---- 内容解压 ----

def decompress_content(content, ct):
    if ct and ct == 4 and isinstance(content, bytes):
        try:
            return _zstd_dctx.decompress(content).decode('utf-8', errors='replace')
        except Exception:
            return None
    if isinstance(content, bytes):
        try:
            return content.decode('utf-8', errors='replace')
        except Exception:
            return None
    return content


# ---- 内容解析 ----

def _parse_message_content(content, local_type, is_group):
    if content is None:
        return '', ''
    if isinstance(content, bytes):
        return '', '(二进制内容)'
    sender = ''
    text = content
    if is_group and ':\n' in content:
        sender, text = content.split(':\n', 1)
    return sender, text


def _collapse_text(text):
    if not text:
        return ''
    return re.sub(r'\s+', ' ', text).strip()


def _parse_xml_root(content):
    if not content or len(content) > _XML_PARSE_MAX_LEN or _XML_UNSAFE_RE.search(content):
        return None
    try:
        return ET.fromstring(content)
    except ET.ParseError:
        return None


def _parse_int(value, fallback=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _format_app_message_text(content, local_type, is_group, chat_username, chat_display_name, names, _display_name_fn, resolve_media=False, db_dir=None, create_time_ts=0):
    if not content or '<appmsg' not in content:
        return None
    _, sub_type = _split_msg_type(local_type)
    root = _parse_xml_root(content)
    if root is None:
        return None
    appmsg = root.find('.//appmsg')
    if appmsg is None:
        return None
    title = _collapse_text(appmsg.findtext('title') or '')
    app_type = _parse_int((appmsg.findtext('type') or '').strip(), _parse_int(sub_type, 0))

    if app_type == 57:
        ref = appmsg.find('.//refermsg')
        ref_content = ''
        ref_display_name = ''
        if ref is not None:
            ref_display_name = (ref.findtext('displayname') or '').strip()
            ref_content = _collapse_text(ref.findtext('content') or '')
        if len(ref_content) > 160:
            ref_content = ref_content[:160] + "..."
        quote_text = title or "[引用消息]"
        if ref_content:
            prefix = f"回复 {ref_display_name}: " if ref_display_name else "回复: "
            quote_text += f"\n  -> {prefix}{ref_content}"
        return quote_text
    if app_type == 6:
        # Try to resolve file path
        if resolve_media and db_dir:
            msg_dir = os.path.join(os.path.dirname(db_dir), "msg", "file")
            if title and os.path.isdir(msg_dir):
                from datetime import datetime as _dt
                dt = _dt.fromtimestamp(create_time_ts) if create_time_ts else None
                if dt:
                    file_dir = os.path.join(msg_dir, dt.strftime("%Y-%m"))
                    if os.path.isdir(file_dir):
                        target = os.path.join(file_dir, title)
                        if os.path.isfile(target):
                            return f"[文件] {title}\n  {target}"
                        # Fuzzy match
                        for f in os.listdir(file_dir):
                            if title in f or f in title:
                                return f"[文件] {title}\n  {os.path.join(file_dir, f)}"
        return f"[文件] {title}" if title else "[文件]"
    if app_type == 5:
        return f"[链接] {title}" if title else "[链接]"
    if app_type in (33, 36, 44):
        return f"[小程序] {title}" if title else "[小程序]"
    if title:
        return f"[链接/文件] {title}"
    return "[链接/文件]"


def _format_voip_message_text(content):
    if not content or '<voip' not in content:
        return None
    root = _parse_xml_root(content)
    if root is None:
        return "[通话]"
    raw_text = _collapse_text(root.findtext('.//msg') or '')
    if not raw_text:
        return "[通话]"
    status_map = {
        'Canceled': '已取消', 'Line busy': '对方忙线',
        'Call not answered': '未接听', "Call wasn't answered": '未接听',
    }
    if raw_text.startswith('Duration:'):
        duration = raw_text.split(':', 1)[1].strip()
        return f"[通话] 通话时长 {duration}" if duration else "[通话]"
    return f"[通话] {status_map.get(raw_text, raw_text)}"


def _resolve_media_path(db_dir, content, local_type, create_time_ts, chat_username=None):
    """尝试解析媒体文件在磁盘上的路径。

    Args:
        db_dir: 微信 db_storage 目录
        content: 解压后的 message_content
        local_type: 消息类型
        create_time_ts: 消息时间戳
        chat_username: 聊天对象 username（用于定位 attach 子目录）

    Returns:
        (path, exists) 元组，path 为 None 表示无法解析
    """
    base_type = local_type & 0xFFFFFFFF
    wechat_base = os.path.dirname(db_dir)
    msg_dir = os.path.join(wechat_base, "msg")
    if not os.path.isdir(msg_dir):
        return None, False

    from datetime import datetime
    dt = datetime.fromtimestamp(create_time_ts)
    date_prefix = dt.strftime("%Y-%m")

    # 文件消息 (type 49, sub 6): msg/file/YYYY-MM/filename
    if base_type == 49 and content:
        root = _parse_xml_root(content)
        if root is not None:
            appmsg = root.find('.//appmsg')
            if appmsg is not None:
                app_type = _parse_int((appmsg.findtext('type') or '').strip())
                if app_type == 6:
                    title = (appmsg.findtext('title') or '').strip()
                    if title:
                        file_dir = os.path.join(msg_dir, "file", date_prefix)
                        if os.path.isdir(file_dir):
                            # 精确匹配文件名
                            target = os.path.join(file_dir, title)
                            if os.path.isfile(target):
                                return target, True
                            # 模糊匹配（文件名可能有细微差异）
                            for f in os.listdir(file_dir):
                                if title in f or f in title:
                                    return os.path.join(file_dir, f), True
        return None, False

    # 图片消息 (type 3): msg/attach/<hash>/YYYY-MM/Img/*.dat
    # 视频/语音消息: msg/video/YYYY-MM/ 或 msg/attach/
    if base_type in (3, 34, 43):
        # 搜索 attach 目录下对应月份的文件
        attach_dir = os.path.join(msg_dir, "attach")
        if not os.path.isdir(attach_dir):
            return None, False

        # 尝试用 chat_username 的 MD5 匹配 attach 子目录
        target_hash = None
        if chat_username:
            h = hashlib.md5(chat_username.encode()).hexdigest()
            candidate = os.path.join(attach_dir, h)
            if os.path.isdir(candidate):
                target_hash = h

        # 限定搜索范围：目标目录或所有目录
        search_dirs = [target_hash] if target_hash else [
            d for d in os.listdir(attach_dir)
            if os.path.isdir(os.path.join(attach_dir, d))
        ]

        sub_dir_name = "Img" if base_type == 3 else ("Video" if base_type == 43 else "Voice")

        for d in search_dirs:
            sub = os.path.join(attach_dir, d, date_prefix, sub_dir_name)
            if os.path.isdir(sub):
                files = [f for f in os.listdir(sub) if not f.endswith("_h.dat")]
                if files:
                    # 返回目录路径（具体是哪个文件无法从 XML 精确匹配）
                    sample = files[0]
                    return os.path.join(sub, sample), True

        # 视频：也检查 msg/video/
        if base_type == 43:
            video_dir = os.path.join(msg_dir, "video", date_prefix)
            if os.path.isdir(video_dir):
                thumbs = [f for f in os.listdir(video_dir) if f.endswith("_thumb.jpg")]
                if thumbs:
                    return os.path.join(video_dir, thumbs[0]), True

    return None, False


def _format_message_text(local_id, local_type, content, is_group, chat_username, chat_display_name, names, display_name_fn, db_dir=None, create_time_ts=0, resolve_media=False):
    sender, text = _parse_message_content(content, local_type, is_group)
    base_type, _ = _split_msg_type(local_type)

    media_path = None
    media_exists = False
    if resolve_media and db_dir and content:
        try:
            media_path, media_exists = _resolve_media_path(
                db_dir, content, local_type, create_time_ts, chat_username
            )
        except Exception:
            pass

    if base_type == 3:
        if media_path:
            tag = f"[图片] {media_path}"
            if not media_exists:
                tag += " (文件不存在)"
        else:
            tag = f"[图片] (local_id={local_id})"
        text = tag
    elif base_type == 47:
        text = "[表情]"
    elif base_type == 50:
        text = _format_voip_message_text(text) or "[通话]"
    elif base_type == 49:
        text = _format_app_message_text(
            text, local_type, is_group, chat_username, chat_display_name, names, display_name_fn,
            resolve_media=resolve_media, db_dir=db_dir, create_time_ts=create_time_ts
        ) or "[链接/文件]"
    elif base_type != 1:
        type_label = format_msg_type(local_type)
        text = f"[{type_label}] {text}" if text else f"[{type_label}]"
    return sender, text


# ---- Name2Id ----

def _load_name2id_maps(conn):
    return messages_repo.load_name2id_map(conn)


# ---- 发送者解析 ----

def _resolve_sender_label(real_sender_id, sender_from_content, is_group, chat_username, chat_display_name, names, id_to_username, display_name_fn):
    sender_username = id_to_username.get(real_sender_id, '')
    if is_group:
        if sender_username and sender_username != chat_username:
            return display_name_fn(sender_username, names)
        if sender_from_content:
            return display_name_fn(sender_from_content, names)
        return ''
    if sender_username == chat_username:
        return chat_display_name
    if sender_username:
        return display_name_fn(sender_username, names)
    return ''


# ---- SQL 查询 ----

def _build_message_filters(start_ts=None, end_ts=None, keyword='', msg_type_filter=None):
    return messages_repo.build_message_filters(
        start_ts=start_ts,
        end_ts=end_ts,
        keyword=keyword,
        msg_type_filter=msg_type_filter,
    )


def _query_messages(conn, table_name, start_ts=None, end_ts=None, keyword='', limit=20, offset=0, msg_type_filter=None):
    return messages_repo.query_messages(
        conn,
        table_name,
        start_ts=start_ts,
        end_ts=end_ts,
        keyword=keyword,
        limit=limit,
        offset=offset,
        msg_type_filter=msg_type_filter,
    )


# ---- 时间解析 ----

def parse_time_value(value, field_name, is_end=False):
    value = (value or '').strip()
    if not value:
        return None
    formats = [
        ('%Y-%m-%d %H:%M:%S', False),
        ('%Y-%m-%d %H:%M', False),
        ('%Y-%m-%d', True),
    ]
    for fmt, date_only in formats:
        try:
            dt = datetime.strptime(value, fmt)
            if date_only and is_end:
                dt = dt.replace(hour=23, minute=59, second=59)
            return int(dt.timestamp())
        except ValueError:
            continue
    raise ValueError(f"{field_name} 格式无效: {value}。支持 YYYY-MM-DD / YYYY-MM-DD HH:MM / YYYY-MM-DD HH:MM:SS")


def parse_time_range(start_time='', end_time=''):
    start_ts = parse_time_value(start_time, 'start_time', is_end=False)
    end_ts = parse_time_value(end_time, 'end_time', is_end=True)
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        raise ValueError('start_time 不能晚于 end_time')
    return start_ts, end_ts


def validate_pagination(limit, offset=0, limit_max=_QUERY_LIMIT_MAX):
    if limit <= 0:
        raise ValueError("limit 必须大于 0")
    if limit_max is not None and limit > limit_max:
        raise ValueError(f"limit 不能大于 {limit_max}")
    if offset < 0:
        raise ValueError("offset 不能小于 0")


# ---- 聊天上下文 ----

def _build_chat_context(query, username, names, message_tables):
    display_name = names.get(username, username)
    if not message_tables:
        return {
            'query': query,
            'username': username,
            'display_name': display_name,
            'db_path': None,
            'table_name': None,
            'message_tables': [],
            'is_group': '@chatroom' in username,
        }

    primary = message_tables[0]
    return {
        'query': query,
        'username': username,
        'display_name': display_name,
        'db_path': primary['db_path'],
        'table_name': primary['table_name'],
        'message_tables': message_tables,
        'is_group': '@chatroom' in username,
    }


def resolve_chat_context(chat_name, msg_db_keys, cache, decrypted_dir, names=None):
    from .contacts import get_contact_names, resolve_username_from_names

    if names is None:
        names = get_contact_names(cache, decrypted_dir)

    username = resolve_username_from_names(chat_name, names)
    if not username:
        return None

    message_tables = _find_msg_tables_for_user(username, msg_db_keys, cache)
    return _build_chat_context(chat_name, username, names, message_tables)


def _iter_table_contexts(ctx):
    tables = ctx.get('message_tables') or []
    if not tables and ctx.get('db_path') and ctx.get('table_name'):
        tables = [{'db_path': ctx['db_path'], 'table_name': ctx['table_name']}]
    for table in tables:
        yield {
            'query': ctx['query'], 'username': ctx['username'], 'display_name': ctx['display_name'],
            'db_path': table['db_path'], 'table_name': table['table_name'],
            'is_group': ctx['is_group'],
        }


def _candidate_page_size(limit, offset):
    return limit + offset


def _page_ranked_entries(entries, limit, offset):
    ordered = sorted(entries, key=lambda item: item[0], reverse=True)
    paged = ordered[offset:offset + limit]
    paged.sort(key=lambda item: item[0])
    return paged


# ---- 构建行 ----

def _build_history_line(row, ctx, names, id_to_username, display_name_fn, resolve_media=False, db_dir=None):
    local_id, local_type, create_time, real_sender_id, content, ct = row
    time_str = datetime.fromtimestamp(create_time).strftime('%Y-%m-%d %H:%M')
    content = decompress_content(content, ct)
    if content is None:
        content = '(无法解压)'
    sender, text = _format_message_text(
        local_id, local_type, content, ctx['is_group'], ctx['username'], ctx['display_name'], names, display_name_fn,
        db_dir=db_dir, create_time_ts=create_time, resolve_media=resolve_media,
    )
    sender_label = _resolve_sender_label(
        real_sender_id, sender, ctx['is_group'], ctx['username'], ctx['display_name'], names, id_to_username, display_name_fn
    )
    if sender_label:
        return create_time, f'[{time_str}] {sender_label}: {text}'
    return create_time, f'[{time_str}] {text}'


def _build_search_entry(row, ctx, names, id_to_username, display_name_fn, resolve_media=False, db_dir=None):
    local_id, local_type, create_time, real_sender_id, content, ct = row
    content = decompress_content(content, ct)
    if content is None:
        return None
    sender, text = _format_message_text(
        local_id, local_type, content, ctx['is_group'], ctx['username'], ctx['display_name'], names, display_name_fn,
        db_dir=db_dir, create_time_ts=create_time, resolve_media=resolve_media,
    )
    if text and len(text) > 300:
        text = text[:300] + '...'
    sender_label = _resolve_sender_label(
        real_sender_id, sender, ctx['is_group'], ctx['username'], ctx['display_name'], names, id_to_username, display_name_fn
    )
    time_str = datetime.fromtimestamp(create_time).strftime('%Y-%m-%d %H:%M')
    entry = f"[{time_str}] [{ctx['display_name']}]"
    if sender_label:
        entry += f" {sender_label}:"
    entry += f" {text}"
    return create_time, entry


# ---- 聊天记录查询 ----

def collect_chat_history(ctx, names, display_name_fn, start_ts=None, end_ts=None, limit=20, offset=0, msg_type_filter=None, resolve_media=False, db_dir=None):
    collected = []
    failures = []
    candidate_limit = _candidate_page_size(limit, offset)
    batch_size = min(candidate_limit, _HISTORY_QUERY_BATCH_SIZE)

    for table_ctx in _iter_table_contexts(ctx):
        try:
            with messages_repo.open_message_db(table_ctx['db_path']) as conn:
                id_to_username = _load_name2id_maps(conn)
                fetch_offset = 0
                before = len(collected)
                while len(collected) - before < candidate_limit:
                    rows = _query_messages(conn, table_ctx['table_name'], start_ts=start_ts, end_ts=end_ts, limit=batch_size, offset=fetch_offset, msg_type_filter=msg_type_filter)
                    if not rows:
                        break
                    fetch_offset += len(rows)
                    for row in rows:
                        try:
                            collected.append(_build_history_line(row, table_ctx, names, id_to_username, display_name_fn, resolve_media=resolve_media, db_dir=db_dir))
                        except Exception as e:
                            failures.append(f"local_id={row[0]}: {e}")
                        if len(collected) - before >= candidate_limit:
                            break
                    if len(rows) < batch_size:
                        break
        except Exception as e:
            failures.append(f"{table_ctx['db_path']}: {e}")

    paged = _page_ranked_entries(collected, limit, offset)
    return [line for _, line in paged], failures


# ---- 搜索查询 ----

def _collect_search_entries(conn, contexts, names, keyword, display_name_fn, start_ts=None, end_ts=None, candidate_limit=20, msg_type_filter=None):
    collected = []
    failures = []
    id_to_username = _load_name2id_maps(conn)
    batch_size = candidate_limit

    for ctx in contexts:
        try:
            fetch_offset = 0
            before = len(collected)
            while len(collected) - before < candidate_limit:
                rows = _query_messages(conn, ctx['table_name'], start_ts=start_ts, end_ts=end_ts, keyword=keyword, limit=batch_size, offset=fetch_offset, msg_type_filter=msg_type_filter)
                if not rows:
                    break
                fetch_offset += len(rows)
                for row in rows:
                    formatted = _build_search_entry(row, ctx, names, id_to_username, display_name_fn)
                    if formatted:
                        collected.append(formatted)
                        if len(collected) - before >= candidate_limit:
                            break
                if len(rows) < batch_size:
                    break
        except Exception as e:
            failures.append(f"{ctx['display_name']}: {e}")
    return collected, failures


def collect_chat_search(ctx, names, keyword, display_name_fn, start_ts=None, end_ts=None, candidate_limit=20, msg_type_filter=None):
    collected = []
    failures = []
    contexts_by_db = {}
    for table_ctx in _iter_table_contexts(ctx):
        contexts_by_db.setdefault(table_ctx['db_path'], []).append(table_ctx)

    for db_path, db_contexts in contexts_by_db.items():
        try:
            with messages_repo.open_message_db(db_path) as conn:
                db_entries, db_failures = _collect_search_entries(
                    conn, db_contexts, names, keyword, display_name_fn,
                    start_ts=start_ts, end_ts=end_ts, candidate_limit=candidate_limit,
                    msg_type_filter=msg_type_filter,
                )
                collected.extend(db_entries)
                failures.extend(db_failures)
        except Exception as e:
            failures.extend(f"{tc['display_name']}: {e}" for tc in db_contexts)
    return collected, failures


def search_all_messages(msg_db_keys, cache, names, keyword, display_name_fn, start_ts=None, end_ts=None, candidate_limit=20, msg_type_filter=None):
    collected = []
    failures = []
    for rel_key in msg_db_keys:
        try:
            db_index = _load_message_db_index(rel_key, cache)
            if not db_index:
                continue
            contexts = _load_search_contexts_from_db(db_index, names)
            with messages_repo.open_message_db(db_index['db_path']) as conn:
                db_entries, db_failures = _collect_search_entries(
                    conn, contexts, names, keyword, display_name_fn,
                    start_ts=start_ts, end_ts=end_ts, candidate_limit=candidate_limit,
                    msg_type_filter=msg_type_filter,
                )
                collected.extend(db_entries)
                failures.extend(db_failures)
        except Exception as e:
            failures.append(f"{rel_key}: {e}")
    return collected, failures


def _load_search_contexts_from_db(db_index, names):
    return _build_search_contexts_from_index(db_index, names)


# ---- 多聊天上下文解析 ----

def resolve_chat_contexts(chat_names, msg_db_keys, cache, decrypted_dir):
    from .contacts import get_contact_names, resolve_username_from_names

    names = get_contact_names(cache, decrypted_dir)
    resolved = []
    unresolved = []
    missing_tables = []
    seen = set()
    queries = []
    for chat_name in chat_names:
        name = (chat_name or '').strip()
        if not name:
            unresolved.append('(空)')
            continue
        username = resolve_username_from_names(name, names)
        if not username:
            unresolved.append(name)
            continue
        queries.append((name, username))

    tables_by_user = _find_msg_tables_for_users(
        [username for _, username in queries],
        msg_db_keys,
        cache,
    )

    for query, username in queries:
        ctx = _build_chat_context(query, username, names, tables_by_user.get(username, []))
        if not ctx['message_tables']:
            missing_tables.append(ctx['display_name'])
            continue
        if ctx['username'] in seen:
            continue
        seen.add(ctx['username'])
        resolved.append(ctx)
    return resolved, unresolved, missing_tables


# ---- 聊天统计 ----

def collect_chat_stats(ctx, names, display_name_fn, start_ts=None, end_ts=None):
    """聚合统计指定聊天的消息数据。

    返回: {
        total, type_breakdown: {type_name: count},
        top_senders: [{name, count}],
        hourly: {0:N, ..., 23:N}
    }
    """
    type_map = {
        1: '文本', 3: '图片', 34: '语音', 42: '名片',
        43: '视频', 47: '表情', 48: '位置', 49: '链接/文件',
        50: '通话', 10000: '系统', 10002: '撤回',
    }

    total = 0
    type_counts = {}
    sender_counts = {}
    hourly_counts = {}
    failures = []

    for table_ctx in _iter_table_contexts(ctx):
        try:
            with messages_repo.open_message_db(table_ctx['db_path']) as conn:
                id_to_username = _load_name2id_maps(conn)
                tbl = table_ctx['table_name']
                for bt, cnt in messages_repo.query_type_counts(
                    conn,
                    tbl,
                    start_ts=start_ts,
                    end_ts=end_ts,
                ):
                    label = type_map.get(bt, f'type={bt}')
                    type_counts[label] = type_counts.get(label, 0) + cnt
                    total += cnt

                for sid, cnt in messages_repo.query_sender_counts(
                    conn,
                    tbl,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    limit=20,
                ):
                    uname = id_to_username.get(sid, str(sid))
                    if uname:
                        sender_counts[uname] = sender_counts.get(uname, 0) + cnt

                for h, cnt in messages_repo.query_hourly_counts(
                    conn,
                    tbl,
                    start_ts=start_ts,
                    end_ts=end_ts,
                ):
                    if h is not None:
                        hourly_counts[h] = hourly_counts.get(h, 0) + cnt
        except Exception as e:
            failures.append(f"{table_ctx['display_name']}: {e}")

    top_senders = sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    top_senders = [{'name': display_name_fn(u, names), 'count': c} for u, c in top_senders]

    hourly = {h: hourly_counts.get(h, 0) for h in range(24)}

    return {
        'total': total,
        'type_breakdown': dict(sorted(type_counts.items(), key=lambda x: x[1], reverse=True)),
        'top_senders': top_senders,
        'hourly': hourly,
        'failures': failures or None,
    }
