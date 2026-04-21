import json
import os
import tempfile
import unittest
from unittest import mock

from wechat_cli.core import db_cache


REL_KEY = os.path.join("session", "session.db")
SECOND_REL_KEY = os.path.join("contact", "contact.db")
TEST_KEYS = {
    REL_KEY: {"enc_key": "00" * 32},
    SECOND_REL_KEY: {"enc_key": "11" * 32},
}


def _create_encrypted_db(db_dir, rel_key=REL_KEY):
    db_path = os.path.join(db_dir, rel_key)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with open(db_path, "wb") as f:
        f.write(b"encrypted-db")
    return db_path


def _fake_full_decrypt(db_path, out_path, enc_key):
    del enc_key
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(b"decrypted:" + os.path.basename(db_path).encode("utf-8"))
    return 1


class DBCacheTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)

        self.cache_dir = os.path.join(self._tmpdir.name, "cache")
        self.index_file = os.path.join(self.cache_dir, "_index.json")
        self._cache_dir_patch = mock.patch.object(db_cache.DBCache, "CACHE_DIR", self.cache_dir)
        self._index_patch = mock.patch.object(db_cache.DBCache, "MTIME_FILE", self.index_file)
        self._cache_dir_patch.start()
        self._index_patch.start()
        self.addCleanup(self._cache_dir_patch.stop)
        self.addCleanup(self._index_patch.stop)

    def test_cache_paths_are_namespaced_by_db_dir(self):
        db_dir_a = os.path.join(self._tmpdir.name, "account_a", "db_storage")
        db_dir_b = os.path.join(self._tmpdir.name, "account_b", "db_storage")
        _create_encrypted_db(db_dir_a)
        _create_encrypted_db(db_dir_b)

        with mock.patch.object(db_cache, "full_decrypt", side_effect=_fake_full_decrypt) as full_decrypt:
            with mock.patch.object(db_cache, "decrypt_wal", return_value=0):
                cache_a = db_cache.DBCache(TEST_KEYS, db_dir_a)
                cache_b = db_cache.DBCache(TEST_KEYS, db_dir_b)
                path_a = cache_a.get(REL_KEY)
                path_b = cache_b.get(REL_KEY)

        self.assertNotEqual(path_a, path_b)
        self.assertEqual(full_decrypt.call_count, 2)
        with open(self.index_file, encoding="utf-8") as f:
            index = json.load(f)
        self.assertEqual(len(index["namespaces"]), 2)
        self.assertEqual(
            {entry["db_dir"] for entry in index["namespaces"].values()},
            {os.path.abspath(db_dir_a), os.path.abspath(db_dir_b)},
        )

    def test_persistent_cache_reloads_without_redecrypting(self):
        db_dir = os.path.join(self._tmpdir.name, "account", "db_storage")
        _create_encrypted_db(db_dir)

        with mock.patch.object(db_cache, "full_decrypt", side_effect=_fake_full_decrypt) as full_decrypt:
            with mock.patch.object(db_cache, "decrypt_wal", return_value=0):
                first_cache = db_cache.DBCache(TEST_KEYS, db_dir)
                first_path = first_cache.get(REL_KEY)

        self.assertEqual(full_decrypt.call_count, 1)

        with mock.patch.object(db_cache, "full_decrypt", side_effect=AssertionError("unexpected decrypt")):
            with mock.patch.object(db_cache, "decrypt_wal", return_value=0):
                second_cache = db_cache.DBCache(TEST_KEYS, db_dir)
                second_path = second_cache.get(REL_KEY)

        self.assertEqual(second_path, first_path)

    def test_persistent_index_merges_entries_from_other_instances(self):
        db_dir = os.path.join(self._tmpdir.name, "account", "db_storage")
        _create_encrypted_db(db_dir, REL_KEY)
        _create_encrypted_db(db_dir, SECOND_REL_KEY)

        with mock.patch.object(db_cache, "full_decrypt", side_effect=_fake_full_decrypt):
            with mock.patch.object(db_cache, "decrypt_wal", return_value=0):
                first_cache = db_cache.DBCache(TEST_KEYS, db_dir)
                second_cache = db_cache.DBCache(TEST_KEYS, db_dir)
                first_path = first_cache.get(REL_KEY)
                second_path = second_cache.get(SECOND_REL_KEY)

        with open(self.index_file, encoding="utf-8") as f:
            index = json.load(f)
        entries = next(iter(index["namespaces"].values()))["entries"]
        self.assertEqual(set(entries), {REL_KEY, SECOND_REL_KEY})
        self.assertEqual(entries[REL_KEY]["path"], first_path)
        self.assertEqual(entries[SECOND_REL_KEY]["path"], second_path)

    def test_cleanup_prunes_orphan_files_in_namespace(self):
        db_dir = os.path.join(self._tmpdir.name, "account", "db_storage")
        _create_encrypted_db(db_dir)

        with mock.patch.object(db_cache, "full_decrypt", side_effect=_fake_full_decrypt):
            with mock.patch.object(db_cache, "decrypt_wal", return_value=0):
                cache = db_cache.DBCache(TEST_KEYS, db_dir)
                live_path = cache.get(REL_KEY)

        orphan_path = os.path.join(cache._namespace_dir, "orphan.db")
        with open(orphan_path, "wb") as f:
            f.write(b"orphan")

        cache.cleanup()

        self.assertTrue(os.path.exists(live_path))
        self.assertFalse(os.path.exists(orphan_path))
        with open(self.index_file, encoding="utf-8") as f:
            index = json.load(f)
        entries = next(iter(index["namespaces"].values()))["entries"]
        self.assertEqual(entries[REL_KEY]["path"], live_path)

    def test_expired_cache_file_is_redecrypted_when_ttl_elapsed(self):
        db_dir = os.path.join(self._tmpdir.name, "account", "db_storage")
        _create_encrypted_db(db_dir)

        with mock.patch.object(db_cache, "full_decrypt", side_effect=_fake_full_decrypt):
            with mock.patch.object(db_cache, "decrypt_wal", return_value=0):
                first_cache = db_cache.DBCache(TEST_KEYS, db_dir, retention_seconds=1)
                cache_path = first_cache.get(REL_KEY)

        expired_ts = 1_600_000_000
        os.utime(cache_path, (expired_ts, expired_ts))

        with mock.patch.object(db_cache, "full_decrypt", side_effect=_fake_full_decrypt) as full_decrypt:
            with mock.patch.object(db_cache, "decrypt_wal", return_value=0):
                second_cache = db_cache.DBCache(TEST_KEYS, db_dir, retention_seconds=1)
                second_path = second_cache.get(REL_KEY)

        self.assertEqual(second_path, cache_path)
        self.assertEqual(full_decrypt.call_count, 1)
        self.assertGreater(os.path.getmtime(second_path), expired_ts)

    def test_cache_can_be_persisted_without_ttl_expiration(self):
        db_dir = os.path.join(self._tmpdir.name, "account", "db_storage")
        _create_encrypted_db(db_dir)

        with mock.patch.object(db_cache, "full_decrypt", side_effect=_fake_full_decrypt):
            with mock.patch.object(db_cache, "decrypt_wal", return_value=0):
                first_cache = db_cache.DBCache(TEST_KEYS, db_dir, retention_seconds=None)
                cache_path = first_cache.get(REL_KEY)

        old_ts = 1_600_000_000
        os.utime(cache_path, (old_ts, old_ts))

        with mock.patch.object(db_cache, "full_decrypt", side_effect=AssertionError("unexpected decrypt")):
            with mock.patch.object(db_cache, "decrypt_wal", return_value=0):
                second_cache = db_cache.DBCache(TEST_KEYS, db_dir, retention_seconds=None)
                second_path = second_cache.get(REL_KEY)

        self.assertEqual(second_path, cache_path)
        self.assertGreater(os.path.getmtime(second_path), old_ts)


if __name__ == "__main__":
    unittest.main()
