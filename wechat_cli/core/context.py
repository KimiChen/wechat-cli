"""应用上下文 — 单例持有配置、缓存、密钥等共享状态"""

import atexit
import json
import os

from .config import load_config, STATE_DIR
from .db_cache import DBCache
from .key_utils import strip_key_metadata
from .messages import find_msg_db_keys


class AppContext:
    """每次 CLI 调用初始化一次，被所有命令共享。"""

    def __init__(self, config_path=None):
        self.cfg = load_config(config_path)
        self.db_dir = self.cfg["db_dir"]
        self.decrypted_dir = self.cfg["decrypted_dir"]
        self.keys_file = self.cfg["keys_file"]

        if not os.path.exists(self.keys_file):
            raise FileNotFoundError(
                f"密钥文件不存在: {self.keys_file}\n"
                "请运行: wechat-cli init"
            )

        with open(self.keys_file, encoding="utf-8") as f:
            self.all_keys = strip_key_metadata(json.load(f))

        retention_seconds = None
        if not self.cfg.get("persist_decrypted_cache"):
            retention_seconds = self.cfg.get("decrypted_cache_ttl_hours", 24) * 3600

        self.cache = DBCache(
            self.all_keys,
            self.db_dir,
            retention_seconds=retention_seconds,
        )
        atexit.register(self.cache.cleanup)

        self.msg_db_keys = find_msg_db_keys(self.all_keys)

        # 确保状态目录存在
        os.makedirs(STATE_DIR, exist_ok=True)

    def display_name_fn(self, username, names):
        from .contacts import display_name_for_username
        return display_name_for_username(username, names, self.db_dir, self.cache, self.decrypted_dir)
