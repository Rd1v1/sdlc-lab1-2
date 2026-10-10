import contextlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from lab1.src import app
from lab1.src.safe_file_manager import AuditStore, SafeFileManager, SafeFileError


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.audit = AuditStore(self.base / "audit.db")
        self.user = self.audit.create_user("demo", "demo password")
        self.fm = SafeFileManager(self.base / "files", self.audit)

    def tearDown(self):
        self.audit.close()
        self.temp.cleanup()

    def test_unicode_spaces_relative_and_xml_roundtrip(self):
        name = "папка с пробелом/данные.xml"
        self.fm.write_xml(name, '<root><name>Привет</name></root>', self.user)
        self.assertEqual(self.fm.read_xml(name, self.user).findtext("name"), "Привет")
        self.assertEqual(len(self.fm.list_files(self.user)), 1)
        self.fm.create_zip("unicode.zip", [name], self.user)
        self.fm.extract_zip("unicode.zip", "out", self.user)
        self.assertEqual(self.fm.read_xml("out/" + name, self.user).tag, "root")

    def test_path_and_file_type_boundaries(self):
        for name in ("", ".", "../escape", "C:relative", "data:stream", "NUL.txt", "bad. ", str(self.base / "absolute")):
            with self.subTest(name=name), self.assertRaises(SafeFileError):
                self.fm.write_text(name, "no", self.user)
        (self.fm.root / "directory").mkdir()
        for name in ("missing", "directory"):
            with self.subTest(name=name), self.assertRaises(SafeFileError):
                self.fm.read_text(name, self.user)

    def test_archive_never_overwrites_even_unregistered_file(self):
        self.fm.write_text("a", "original", self.user)
        self.fm.create_zip("a.zip", ["a"], self.user)
        with self.assertRaises(SafeFileError):
            self.fm.create_zip("a.zip", ["a"], self.user)
        destination = self.fm.root / "out"
        destination.mkdir()
        (destination / "a").write_text("preserve", encoding="utf-8")
        with self.assertRaises(SafeFileError):
            self.fm.extract_zip("a.zip", "out", self.user)
        self.assertEqual((destination / "a").read_text(), "preserve")

    def test_archive_rejects_windows_traversal_before_writing(self):
        path = self.fm.root / "evil.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("good", "ok")
            archive.writestr("..\\evil", "no")
        self.audit.record_file("evil.zip", path.stat().st_size, self.user, "write")
        with self.assertRaises(SafeFileError):
            self.fm.extract_zip("evil.zip", "out", self.user)
        self.assertFalse((self.fm.root / "out/good").exists())

    def test_io_failure_cleans_temporary_file(self):
        with patch("lab1.src.safe_file_manager.os.fsync", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                self.fm.write_text("a", "hello", self.user)
        self.assertEqual(list(self.fm.root.iterdir()), [])

    def test_zip_file_parent_conflict_rejected_before_any_write(self):
        for entries in (('a', 'a/b'), ('a/b', 'a')):
            with self.subTest(entries=entries):
                path = self.fm.root / 'conflict.zip'
                with zipfile.ZipFile(path, 'w') as archive:
                    for member in entries:
                        archive.writestr(member, 'payload')
                self.audit.record_file('conflict.zip', path.stat().st_size, self.user, 'write')
                with self.assertRaises(SafeFileError):
                    self.fm.extract_zip('conflict.zip', 'out', self.user)
                self.assertFalse((self.fm.root / 'out').exists())

    def test_zip_preserves_empty_directories(self):
        path = self.fm.root / 'empty.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('empty/nested/', '')
        self.audit.record_file('empty.zip', path.stat().st_size, self.user, 'write')
        self.assertEqual([], self.fm.extract_zip('empty.zip', 'out', self.user))
        self.assertTrue((self.fm.root / 'out/empty/nested').is_dir())

    def test_cli_permission_errors_and_input(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            for args in ([], ["help"], ["pwd"], ["exit"]):
                self.assertEqual(app.run(args), 0)
            with self.assertRaises(SystemExit) as caught:
                app.run(["not-a-command"])
            self.assertEqual(caught.exception.code, 2)
            with patch.object(app, "AuditStore", side_effect=PermissionError("denied")):
                self.assertEqual(app.run(["register", "demo"]), 2)
        self.assertNotIn("Traceback", output.getvalue())


if __name__ == "__main__":
    unittest.main()
