import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lab1.src.app import run


class CliTests(unittest.TestCase):
    def test_register_write_read_and_authentication_error(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            common = []
            output = io.StringIO()
            with patch("lab1.src.app.DATA_ROOT", base / "files"), patch(
                "lab1.src.app.AUDIT_DATABASE", base / "audit.sqlite3"
            ), patch("lab1.src.app.getpass.getpass", return_value="safe demo password"), contextlib.redirect_stdout(output):
                self.assertEqual(run(common + ["register", "demo"]), 0)
            self.assertIn("Пользователь создан", output.getvalue())

            with patch("lab1.src.app.DATA_ROOT", base / "files"), patch(
                "lab1.src.app.AUDIT_DATABASE", base / "audit.sqlite3"
            ), patch("lab1.src.app.getpass.getpass", return_value="safe demo password"), contextlib.redirect_stdout(output):
                self.assertEqual(run(common + ["write", "note.txt", "--text", "demo data", "--user", "demo"]), 0)
            with patch("lab1.src.app.DATA_ROOT", base / "files"), patch(
                "lab1.src.app.AUDIT_DATABASE", base / "audit.sqlite3"
            ), patch("lab1.src.app.getpass.getpass", return_value="safe demo password"), contextlib.redirect_stdout(output):
                self.assertEqual(run(common + ["read", "note.txt", "--user", "demo"]), 0)
            self.assertIn("demo data", output.getvalue())

            error = io.StringIO()
            with patch("lab1.src.app.DATA_ROOT", base / "files"), patch(
                "lab1.src.app.AUDIT_DATABASE", base / "audit.sqlite3"
            ), patch("lab1.src.app.getpass.getpass", return_value="wrong password"), contextlib.redirect_stderr(error):
                self.assertEqual(run(common + ["read", "note.txt", "--user", "demo"]), 2)
            self.assertIn("Неверный логин или пароль", error.getvalue())


if __name__ == "__main__":
    unittest.main()