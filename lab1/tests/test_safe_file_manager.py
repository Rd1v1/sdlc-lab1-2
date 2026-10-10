import tempfile
import threading
import unittest
import zipfile
import multiprocessing
from pathlib import Path

from lab1.src.safe_file_manager import AuditStore, SafeFileError, SafeFileManager


def _write_from_process(root: str, database: str, payload: str) -> None:
    store = AuditStore(Path(database))
    user_id = store.authenticate("demo", "correct horse battery")
    SafeFileManager(Path(root), store, max_file_bytes=4096, max_archive_bytes=8192).write_text(
        "shared-process.txt", payload, user_id
    )
    store.close()


class SafeFileManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "files"
        self.audit = AuditStore(base / "audit.sqlite3")
        self.user_id = self.audit.create_user("demo", "correct horse battery")
        self.manager = SafeFileManager(self.root, self.audit, max_file_bytes=4096, max_archive_bytes=8192)

    def tearDown(self):
        self.audit.close()
        self.temporary.cleanup()

    def test_password_is_hashed_and_authentication_is_checked(self):
        self.assertEqual(self.audit.authenticate("demo", "correct horse battery"), self.user_id)
        self.assertIsNone(self.audit.authenticate("demo", "wrong password"))
        row = self.audit._connection.execute(
            "SELECT password_hash FROM Users WHERE id = ?", (self.user_id,)
        ).fetchone()
        self.assertNotEqual(row[0], b"correct horse battery")
        self.assertIsNone(self.audit.authenticate("demo' OR 1=1 --", "correct horse battery"))

    def test_crud_uses_safe_root_and_writes_audit(self):
        self.manager.write_text("notes/hello.txt", "hello", self.user_id)
        self.assertEqual(self.manager.read_text("notes/hello.txt", self.user_id), "hello")
        self.manager.write_text("notes/hello.txt", "updated", self.user_id)
        self.manager.delete("notes/hello.txt", self.user_id)
        types = [row[0] for row in self.audit._connection.execute(
            "SELECT operation_type FROM Operations ORDER BY id"
        )]
        self.assertEqual(types, ["register", "create", "read", "modify", "delete"])

    def test_rejects_path_traversal_and_absolute_paths(self):
        for name in ("../outside.txt", "C:\\Windows\\win.ini", "\\\\server\\share\\file"):
            with self.subTest(name=name), self.assertRaises(SafeFileError):
                self.manager.write_text(name, "no", self.user_id)

    def test_rejects_unregistered_files_inside_root(self):
        unregistered = self.root / "outside-managed.txt"
        unregistered.write_text("not in database", encoding="utf-8")
        with self.assertRaises(SafeFileError):
            self.manager.read_text("outside-managed.txt", self.user_id)
        with self.assertRaises(SafeFileError):
            self.manager.write_text("outside-managed.txt", "overwrite", self.user_id)
        self.assertEqual(unregistered.read_text(encoding="utf-8"), "not in database")

    def test_enforces_file_size_limit(self):
        with self.assertRaises(SafeFileError):
            self.manager.write_text("large.txt", "x" * 4097, self.user_id)

    def test_users_cannot_read_or_delete_each_others_files(self):
        other_user = self.audit.create_user("other", "another secure password")
        self.manager.write_text("private.txt", "private", self.user_id)
        with self.assertRaises(SafeFileError):
            self.manager.read_text("private.txt", other_user)
        with self.assertRaises(SafeFileError):
            self.manager.delete("private.txt", other_user)
        self.assertEqual(self.manager.read_text("private.txt", self.user_id), "private")

    def test_copy_and_move_do_not_overwrite_existing_files(self):
        self.manager.write_text("source.txt", "content", self.user_id)
        self.manager.copy_file("source.txt", "copy.txt", self.user_id)
        self.assertEqual(self.manager.read_text("copy.txt", self.user_id), "content")
        with self.assertRaises(SafeFileError):
            self.manager.copy_file("source.txt", "copy.txt", self.user_id)
        self.manager.move_file("source.txt", "moved.txt", self.user_id)
        self.assertEqual(self.manager.read_text("moved.txt", self.user_id), "content")
        with self.assertRaises(SafeFileError):
            self.manager.read_text("source.txt", self.user_id)

    def test_json_round_trip_and_invalid_xml(self):
        value = {"name": "пример", "count": 3}
        self.manager.write_json("data.json", value, self.user_id)
        self.assertEqual(self.manager.read_json("data.json", self.user_id), value)
        with self.assertRaises(SafeFileError):
            self.manager.write_xml("unsafe.xml", '<!DOCTYPE x [<!ENTITY e "boom">]><x>&e;</x>', self.user_id)
        with self.assertRaises(SafeFileError):
            self.manager.write_xml("broken.xml", "<x>", self.user_id)

    def test_zip_create_extract_and_traversal_rejection(self):
        self.manager.write_text("source.txt", "archive content", self.user_id)
        self.manager.create_zip("archive.zip", ["source.txt"], self.user_id)
        self.assertEqual(self.manager.extract_zip("archive.zip", "out", self.user_id), ["out/source.txt"])
        self.assertEqual(self.manager.read_text("out/source.txt", self.user_id), "archive content")

        malicious = self.root / "malicious.zip"
        with zipfile.ZipFile(malicious, "w") as archive:
            archive.writestr("../escaped.txt", "blocked")
        self.audit.record_file("malicious.zip", malicious.stat().st_size, self.user_id, "write")
        with self.assertRaises(SafeFileError):
            self.manager.extract_zip("malicious.zip", "blocked", self.user_id)
        self.assertFalse((self.root.parent / "escaped.txt").exists())

    def test_zip_limits_reject_bomb_ratio_and_oversized_entries(self):
        strict = SafeFileManager(
            self.root, self.audit, max_file_bytes=4096, max_archive_bytes=8192, max_compression_ratio=2
        )
        strict.write_text("repeated.txt", "A" * 2000, self.user_id)
        strict.create_zip("compressed.zip", ["repeated.txt"], self.user_id)
        with self.assertRaises(SafeFileError):
            strict.extract_zip("compressed.zip", "ratio-blocked", self.user_id)

        oversized = self.root / "oversized.zip"
        with zipfile.ZipFile(oversized, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("too-large.txt", "x" * 5000)
        self.audit.record_file("oversized.zip", oversized.stat().st_size, self.user_id, "write")
        with self.assertRaises(SafeFileError):
            strict.extract_zip("oversized.zip", "size-blocked", self.user_id)

    def test_concurrent_writes_are_complete_and_audited(self):
        payloads = [f"value-{index}" for index in range(8)]
        threads = [
            threading.Thread(target=self.manager.write_text, args=("shared.txt", value, self.user_id))
            for value in payloads
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertIn(self.manager.read_text("shared.txt", self.user_id), payloads)
        self.assertEqual(
            self.audit._connection.execute("SELECT COUNT(*) FROM Operations").fetchone()[0], 10
        )

    def test_named_lock_serializes_separate_processes(self):
        context = multiprocessing.get_context("spawn")
        processes = [
            context.Process(
                target=_write_from_process,
                args=(str(self.root), str(Path(self.temporary.name) / "audit.sqlite3"), f"process-{index}"),
            )
            for index in range(2)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=15)
        for process in processes:
            self.assertFalse(process.is_alive(), "Child process did not finish")
            self.assertEqual(process.exitcode, 0)
        self.assertIn(
            (self.root / "shared-process.txt").read_text(encoding="utf-8"),
            {"process-0", "process-1"},
        )
        self.assertEqual(
            self.audit._connection.execute(
                "SELECT COUNT(*) FROM Files WHERE location = 'shared-process.txt'"
            ).fetchone()[0],
            1,
        )


if __name__ == "__main__":
    unittest.main()