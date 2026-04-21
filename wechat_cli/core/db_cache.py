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
    DEFAULT_RETENTION_SECONDS = 24 * 3600

    def __init__(self, all_keys, db_dir, retention_seconds=DEFAULT_RETENTION_SECONDS):
        self._all_keys = all_keys
        self._db_dir = os.path.abspath(db_dir)
        self._retention_seconds = retention_seconds
        self._namespace = hashlib.sha256(self._db_dir.encode("utf-8")).hexdigest()[:16]
        self._namespace_dir = os.path.join(self.CACHE_DIR, self._namespace)
        self._cache = {}  # rel_key -> (db_mtime, wal_mtime, tmp_path)
        os.makedirs(self.CACHE_DIR, exist_ok=True)
        os.makedirs(self._namespace_dir, exist_ok=True)
        self._prune_cache_files()
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

    def _is_expired(self, path, now=None):
        if self._retention_seconds is None or not path or not os.path.exists(path):
            return False
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return False
        if now is None:
            now = time.time()
        return now - mtime > self._retention_seconds

    def _touch_cache_file(self, path):
        try:
            os.utime(path, None)
        except OSError:
            pass

    def _normalize_path(self, path):
        return os.path.normcase(os.path.abspath(path))

    def _can_remove_cache_file(self, path):
        return not os.path.exists(path + ".lock")

    def _current_cached_path(self, rel_key, db_mtime, wal_mtime):
        cached = self._cache.get(rel_key)
        if not cached:
            return None
        cached_db_mtime, cached_wal_mtime, cached_path = cached
        if self._is_expired(cached_path):
            self._cache.pop(rel_key, None)
            return None
        if (
            cached_db_mtime == db_mtime
            and cached_wal_mtime == wal_mtime
            and os.path.exists(cached_path)
        ):
            self._touch_cache_file(cached_path)
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
            if self._is_expired(tmp_path):
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
            if path and os.path.exists(path) and not self._is_expired(path):
                entries[rel_key] = info

        for rel_key, (db_mt, wal_mt, path) in self._cache.items():
            if os.path.exists(path) and not self._is_expired(path):
                entries[rel_key] = {"db_mt": db_mt, "wal_mt": wal_mt, "path": path}

        if entries:
            entry["db_dir"] = self._db_dir
            entry["entries"] = entries
        else:
            index.setdefault("namespaces", {}).pop(self._namespace, None)

        self._save_index(index)

    def _prune_cache_files(self):
        now = time.time()
        index = self._load_index()
        namespaces = index.setdefault("namespaces", {})
        live_paths = set()

        for namespace, entry in list(namespaces.items()):
            entries = entry.get("entries")
            if not isinstance(entries, dict):
                namespaces.pop(namespace, None)
                continue

            kept_entries = {}
            for rel_key, info in entries.items():
                if not isinstance(info, dict):
                    continue
                path = info.get("path")
                if not path or not os.path.exists(path):
                    continue
                if self._is_expired(path, now=now):
                    if self._can_remove_cache_file(path):
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                        continue
                normalized = self._normalize_path(path)
                live_paths.add(normalized)
                kept_entries[rel_key] = info

            if kept_entries:
                entry["entries"] = kept_entries
            else:
                namespaces.pop(namespace, None)

        for name in os.listdir(self.CACHE_DIR):
            path = os.path.join(self.CACHE_DIR, name)
            if not os.path.isdir(path):
                continue
            for filename in os.listdir(path):
                file_path = os.path.join(path, filename)
                if not os.path.isfile(file_path) or not filename.endswith(".db"):
                    continue
                normalized = self._normalize_path(file_path)
                if normalized in live_paths:
                    continue
                if not self._can_remove_cache_file(file_path):
                    continue
                if self._is_expired(file_path, now=now) or normalized not in live_paths:
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass

        self._save_index(index)

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
            self._prune_cache_files()
            return tmp_path
        finally:
            self._release_cache_lock(lock_fd, lock_path)

    def cleanup(self):
        self._save_persistent_cache()
        self._prune_cache_files()

    def describe(self, rel_key):
        path = self.get(rel_key)
        if not path:
            return None

        cached = self._cache.get(rel_key)
        if cached:
            db_mtime, wal_mtime, _ = cached
            return {
                "path": path,
                "db_mtime": db_mtime,
                "wal_mtime": wal_mtime,
                "version_token": (db_mtime, wal_mtime),
            }

        return {
            "path": path,
            "db_mtime": None,
            "wal_mtime": None,
            "version_token": (path,),
        }
