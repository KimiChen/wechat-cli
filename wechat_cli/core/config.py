"""Configuration loading and auto-detection helpers."""

import glob as glob_mod
import json
import os
import platform
import sys

_SYSTEM = platform.system().lower()

if _SYSTEM == "linux":
    _DEFAULT_PROCESS = "wechat"
elif _SYSTEM == "darwin":
    _DEFAULT_PROCESS = "WeChat"
else:
    _DEFAULT_PROCESS = "Weixin.exe"

STATE_DIR = os.path.expanduser("~/.wechat-cli")
CONFIG_FILE = os.path.join(STATE_DIR, "config.json")
KEYS_FILE = os.path.join(STATE_DIR, "all_keys.json")
DEFAULT_DECRYPTED_CACHE_TTL_HOURS = 24


def _coerce_nonnegative_int(value, default):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if value >= 0 else default


def _coerce_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _candidate_mtime(path):
    msg_dir = os.path.join(path, "message")
    target = msg_dir if os.path.isdir(msg_dir) else path
    try:
        return os.path.getmtime(target)
    except OSError:
        return 0


def _sort_candidates(candidates):
    return sorted(candidates, key=_candidate_mtime, reverse=True)


def _choose_candidate(candidates):
    candidates = _sort_candidates(list(candidates))
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        if not sys.stdin.isatty():
            return candidates[0]

        print("[!] 检测到多个微信数据目录:")
        for i, candidate in enumerate(candidates, 1):
            print(f"    {i}. {candidate}")
        print("    0. 跳过")
        print("    直接回车默认选择最近活跃的目录")

        try:
            while True:
                choice = input(f"请选择 [0-{len(candidates)}]: ").strip()
                if choice == "":
                    return candidates[0]
                if choice == "0":
                    return None
                if choice.isdigit() and 1 <= int(choice) <= len(candidates):
                    return candidates[int(choice) - 1]
                print("    无效输入")
        except (EOFError, KeyboardInterrupt):
            print()
            return candidates[0]
    return None


def _auto_detect_db_dir_windows():
    appdata = os.environ.get("APPDATA", "")
    config_dir = os.path.join(appdata, "Tencent", "xwechat", "config")
    if not os.path.isdir(config_dir):
        return None

    data_roots = []
    for ini_file in glob_mod.glob(os.path.join(config_dir, "*.ini")):
        try:
            content = None
            for enc in ("utf-8", "gbk"):
                try:
                    with open(ini_file, "r", encoding=enc) as f:
                        content = f.read(1024).strip()
                    break
                except UnicodeDecodeError:
                    continue
            if not content or any(c in content for c in "\n\r\x00"):
                continue
            if os.path.isdir(content):
                data_roots.append(content)
        except OSError:
            continue

    seen = set()
    candidates = []
    for root in data_roots:
        pattern = os.path.join(root, "xwechat_files", "*", "db_storage")
        for match in glob_mod.glob(pattern):
            normalized = os.path.normcase(os.path.normpath(match))
            if os.path.isdir(match) and normalized not in seen:
                seen.add(normalized)
                candidates.append(match)
    return _choose_candidate(candidates)


def _auto_detect_db_dir_linux():
    seen = set()
    candidates = []
    search_roots = [os.path.expanduser("~/Documents/xwechat_files")]
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        import pwd

        try:
            sudo_home = pwd.getpwnam(sudo_user).pw_dir
        except KeyError:
            sudo_home = None
        if sudo_home:
            fallback = os.path.join(sudo_home, "Documents", "xwechat_files")
            if fallback not in search_roots:
                search_roots.append(fallback)

    for root in search_roots:
        if not os.path.isdir(root):
            continue
        pattern = os.path.join(root, "*", "db_storage")
        for match in glob_mod.glob(pattern):
            normalized = os.path.normcase(os.path.normpath(match))
            if os.path.isdir(match) and normalized not in seen:
                seen.add(normalized)
                candidates.append(match)

    old_path = os.path.expanduser("~/.local/share/weixin/data/db_storage")
    if os.path.isdir(old_path):
        normalized = os.path.normcase(os.path.normpath(old_path))
        if normalized not in seen:
            candidates.append(old_path)

    return _choose_candidate(candidates)


def _auto_detect_db_dir_macos():
    base = os.path.expanduser("~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files")
    if not os.path.isdir(base):
        return None

    seen = set()
    candidates = []
    pattern = os.path.join(base, "*", "db_storage")
    for match in glob_mod.glob(pattern):
        normalized = os.path.normcase(os.path.normpath(match))
        if os.path.isdir(match) and normalized not in seen:
            seen.add(normalized)
            candidates.append(match)
    return _choose_candidate(candidates)


def auto_detect_db_dir():
    if _SYSTEM == "windows":
        return _auto_detect_db_dir_windows()
    if _SYSTEM == "linux":
        return _auto_detect_db_dir_linux()
    if _SYSTEM == "darwin":
        return _auto_detect_db_dir_macos()
    return None


def load_config(config_path=None):
    """Load config, defaulting to ~/.wechat-cli/config.json."""
    if config_path is None:
        config_path = CONFIG_FILE

    cfg = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except json.JSONDecodeError:
            cfg = {}

    db_dir = cfg.get("db_dir", "")
    if not db_dir:
        detected = auto_detect_db_dir()
        if detected:
            cfg["db_dir"] = detected
        else:
            raise FileNotFoundError("未找到微信数据目录。\n请运行 wechat-cli init")

    state_dir = os.path.dirname(os.path.abspath(config_path))
    cfg.setdefault("keys_file", os.path.join(state_dir, "all_keys.json"))
    cfg.setdefault("decrypted_dir", os.path.join(state_dir, "decrypted"))
    cfg.setdefault("decoded_image_dir", os.path.join(state_dir, "decoded_images"))
    cfg.setdefault("wechat_process", _DEFAULT_PROCESS)
    cfg["persist_decrypted_cache"] = _coerce_bool(
        cfg.get("persist_decrypted_cache", False),
        default=False,
    )
    cfg["decrypted_cache_ttl_hours"] = _coerce_nonnegative_int(
        cfg.get("decrypted_cache_ttl_hours", DEFAULT_DECRYPTED_CACHE_TTL_HOURS),
        default=DEFAULT_DECRYPTED_CACHE_TTL_HOURS,
    )

    for key in ("db_dir", "keys_file", "decrypted_dir", "decoded_image_dir"):
        if key in cfg and not os.path.isabs(cfg[key]):
            cfg[key] = os.path.join(state_dir, cfg[key])

    db_dir = cfg.get("db_dir", "")
    if db_dir and os.path.basename(db_dir) == "db_storage":
        cfg["wechat_base_dir"] = os.path.dirname(db_dir)
    else:
        cfg["wechat_base_dir"] = db_dir

    return cfg
