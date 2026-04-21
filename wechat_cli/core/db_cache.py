"""Decrypted database cache with per-account namespacing."""

import hashlib
import json
import os
import tempfile
import time

from .crypto import decrypt_wal, full_decrypt
from .key_utils import get_key_info


class DBCache:
    CACHE_DIR = os.path.join(tempfile.gettempdir(), "wechat_cli_cache")
    MTIME_FILE = os.path.join(CACHE_DIR, "_index.json")

    def __init__(self, all_keys, db_dir):
        self._all_keys = all_keys
        self._db_dir = os.path.abspath(db_dir)
        self._namespace = hashlib.sha256(self._db_dir.encode("utf-8")).hexdigest()[:16]
        self._namespace_dir = os.path.join(self.CACHE_DIR, self._namespace)
        self._cache = {}  # rel_key -> (db_mtime, wal_mtime, tmp_path)
        os.makedirs(self.CACHE_DIR, exist_ok=True)
        os.makedirs(self._namespace_dir, exist_ok=True)
        self._load_persistent_cache()

    def _cache_path(self, rel_key):
        rel_hash = hashlib.md5(rel_key.encode()).hexdigest()[:12]
        return os.path.join(self._namespace_dir, f"{rel_hash}.db")

    def _load_index(self):
        if not os.path.exists(self.MTIME_FILE):
            return {"version": 1, "namespaces": {}}
        try:
            with open(self.MTIME_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"version": 1, "namespaces": {}}
        if not isinstance(data, dict):
            return {"version": 1, "namespaces": {}}
        namespaces = data.get("namespaces")
        if not isinstance(namespaces, dict):
            return {"version": 1, "namespaces": {}}
        return {
            "version": data.get("version", 1),
            "namespaces": namespaces,
        }

    def _save_index(self, index):
        try:
            with open(self.MTIME_FILE, "w", encoding="utf-8") as f:
                json.dump(index, f)
        except OSError:
            pass

    def _namespace_index_entry(self, index):
        namespaces = index.setdefault("namespaces", {})
        entry = namespaces.get(self._namespace)
        if not isinstance(entry, dict) or entry.get("db_dir") != self._db_dir:
            entry = {"db_dir": self._db_dir, "entries": {}}
            namespaces[self._namespace] = entry
        if not isinstance(entry.get("entries"), dict):
            entry["entries"] = {}
        return entry

    def _persistent_paths(self):
        index = self._load_index()
        entry = self._namespace_index_entry(index)
        live_paths = set()
        for info in entry["entries"].values():
            if not isinstance(info, dict):
                continue
            path = info.get("path")
            if path and os.path.exists(path):
                live_paths.add(os.path.normcase(os.path.abspath(path)))
        return live_paths

    def _current_cached_path(self, rel_key, db_mtime, wal_mtime):
        cached = self._cache.get(rel_key)
        if not cached:
            return None
        cached_db_mtime, cached_wal_mtime, cached_path = cached
        if (
            cached_db_mtime == db_mtime
            and cached_wal_mtime == wal_mtime
            and os.path.exists(cached_path)
        ):
            return cached_path
        return None

    def _acquire_cache_lock(self, lock_path, timeout=10.0, interval=0.05):
        deadline = time.time() + timeout
        while True:
            try:
                return os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            except FileExistsError:
                if time.time() >= deadline:
                    raise TimeoutError(f"Timed out waiting for cache lock: {lock_path}")
                time.sleep(interval)

    def _release_cache_lock(self, fd, lock_path):
        try:
            os.close(fd)
        finally:
            try:
                os.remove(lock_path)
            except OSError:
                pass

    def _load_persistent_cache(self):
        index = self._load_index()
        entry = self._namespace_index_entry(index)
        for rel_key, info in entry["entries"].items():
            if not isinstance(info, dict):
                continue
            tmp_path = info.get("path", "")
            if not tmp_path or not os.path.exists(tmp_path):
                continue

            rel_path = rel_key.replace("\\", os.sep)
            db_path = os.path.join(self._db_dir, rel_path)
            wal_path = db_path + "-wal"
            try:
                db_mtime = os.path.getmtime(db_path)
                wal_mtime = os.path.getmtime(wal_path) if os.path.exists(wal_path) else 0
            except OSError:
                continue
            if db_mtime == info.get("db_mt") and wal_mtime == info.get("wal_mt"):
                self._cache[rel_key] = (db_mtime, wal_mtime, tmp_path)

    def _save_persistent_cache(self):
        index = self._load_index()
        entry = self._namespace_index_entry(index)

        entries = {}
        for rel_key, info in entry["entries"].items():
            if not isinstance(info, dict):
                continue
            path = info.get("path")
            if path and os.path.exists(path):
                entries[rel_key] = info

        for rel_key, (db_mt, wal_mt, path) in self._cache.items():
            if os.path.exists(path):
                entries[rel_key] = {"db_mt": db_mt, "wal_mt": wal_mt, "path": path}

        if entries:
            entry["db_dir"] = self._db_dir
            entry["entries"] = entries
        else:
            index.setdefault("namespaces", {}).pop(self._namespace, None)

        self._save_index(index)

    def _prune_namespace_cache_files(self):
        if not os.path.isdir(self._namespace_dir):
            return
        live_paths = self._persistent_paths()
        live_paths.update(
            {
            os.path.normcase(os.path.abspath(path))
            for _, _, path in self._cache.values()
            if os.path.exists(path)
            }
        )
        for name in os.listdir(self._namespace_dir):
            path = os.path.join(self._namespace_dir, name)
            if not os.path.isfile(path) or not name.endswith(".db"):
                continue
            normalized = os.path.normcase(os.path.abspath(path))
            if normalized in live_paths:
                continue
            try:
                os.remove(path)
            except OSError:
                pass

    def get(self, rel_key):
        key_info = get_key_info(self._all_keys, rel_key)
        if not key_info:
            return None

        rel_path = rel_key.replace("\\", "/").replace("/", os.sep)
        db_path = os.path.join(self._db_dir, rel_path)
        wal_path = db_path + "-wal"
        if not os.path.exists(db_path):
            return None

        try:
            db_mtime = os.path.getmtime(db_path)
            wal_mtime = os.path.getmtime(wal_path) if os.path.exists(wal_path) else 0
        except OSError:
            return None

        tmp_path = self._cache_path(rel_key)
        cached_path = self._current_cached_path(rel_key, db_mtime, wal_mtime)
        if cached_path:
            return cached_path

        lock_path = tmp_path + ".lock"
        lock_fd = self._acquire_cache_lock(lock_path)
        enc_key = bytes.fromhex(key_info["enc_key"])
        try:
            self._load_persistent_cache()
            cached_path = self._current_cached_path(rel_key, db_mtime, wal_mtime)
            if cached_path:
                return cached_path

            fd, work_path = tempfile.mkstemp(
                prefix=os.path.basename(tmp_path) + ".",
                suffix=".tmp",
                dir=self._namespace_dir,
            )
            os.close(fd)
            try:
                full_decrypt(db_path, work_path, enc_key)
                if os.path.exists(wal_path):
                    decrypt_wal(wal_path, work_path, enc_key)
                os.replace(work_path, tmp_path)
            except Exception:
                try:
                    os.remove(work_path)
                except OSError:
                    pass
                raise

            self._cache[rel_key] = (db_mtime, wal_mtime, tmp_path)
            self._save_persistent_cache()
            self._prune_namespace_cache_files()
            return tmp_path
        finally:
            self._release_cache_lock(lock_fd, lock_path)

    def cleanup(self):
        self._save_persistent_cache()
        self._prune_namespace_cache_files()
