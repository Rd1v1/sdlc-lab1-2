import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lab1.src import app
from lab1.src.audit import AuditStore
from lab1.src.errors import SafeFileError
from lab1.src.safe_file_manager import SafeFileManager


class XmlSecurityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.database = self.base / "audit.sqlite3"
        self.audit = AuditStore(self.database)
        self.addCleanup(self.audit.close)
        self.password = "correct horse battery"
        self.user_id = self.audit.create_user("demo", self.password)
        self.manager = SafeFileManager(self.base / "files", self.audit)

    def test_normal_xml_entities_namespaces_comments_and_cdata_round_trip(self):
        text = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<root xmlns="urn:demo"><name>Привет &amp; &lt; &gt; &quot; &apos; &#65; &#x42;</name>'
            '<!-- <!ENTITY harmless "comment"> -->'
            '<raw><![CDATA[<!DOCTYPE text>]]></raw></root>'
        )
        self.manager.write_xml("good.xml", text, self.user_id)
        root = self.manager.read_xml("good.xml", self.user_id)
        self.assertEqual(root.tag, "{urn:demo}root")
        self.assertEqual(root.find("{urn:demo}name").text, 'Привет & < > " \' A B')
        self.assertEqual(root.find("{urn:demo}raw").text, "<!DOCTYPE text>")
        self.assertEqual((self.manager.root / "good.xml").read_text(encoding="utf-8"), text)

    def test_dtd_entities_and_small_bomb_are_rejected_on_write_and_read(self):
        secret = self.base / "secret.txt"
        secret.write_text("private-example", encoding="utf-8")
        payloads = (
            '<!DOCTYPE root><root/>',
            '<!DOCTYPE root [<!ENTITY value "example">]><root>&value;</root>',
            f'<!DOCTYPE root [<!ENTITY value SYSTEM "{secret.as_uri()}">]><root>&value;</root>',
            '<!DOCTYPE root SYSTEM "http://127.0.0.1:9/project-example.dtd"><root/>',
            f'<!DOCTYPE root [<!ENTITY % ext SYSTEM "{secret.as_uri()}">%ext;]><root/>',
            '<!DOCTYPE root [<!ENTITY a "ha"><!ENTITY b "&a;&a;">'
            '<!ENTITY c "&b;&b;">]><root>&c;</root>',
        )
        for text in payloads:
            with self.subTest(text=text):
                with self.assertRaisesRegex(SafeFileError, "DTD"):
                    self.manager.write_xml("blocked/new.xml", text, self.user_id)
                self.assertFalse((self.manager.root / "blocked").exists())
                self.manager.write_text("raw.xml", text, self.user_id)
                with self.assertRaisesRegex(SafeFileError, "DTD"):
                    self.manager.read_xml("raw.xml", self.user_id)
        self.assertEqual(secret.read_text(encoding="utf-8"), "private-example")

    def test_oversized_utf8_is_rejected_before_parsing_or_overwriting(self):
        self.manager.max_file_bytes = 64
        self.manager.write_xml("existing.xml", "<r>old</r>", self.user_id)
        text = "<r>" + "я" * 30 + "</r>"
        self.assertLess(len(text), self.manager.max_file_bytes)
        self.assertGreater(len(text.encode("utf-8")), self.manager.max_file_bytes)
        with patch("lab1.src.safe_file_manager.SafeET.fromstring", side_effect=AssertionError("Parser ran")):
            with self.assertRaisesRegex(SafeFileError, "лимит"):
                self.manager.write_xml("existing.xml", text, self.user_id)
            self.assertEqual((self.manager.root / "existing.xml").read_text(encoding="utf-8"), "<r>old</r>")
            (self.manager.root / "existing.xml").write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(SafeFileError, "лимит"):
                self.manager.read_xml("existing.xml", self.user_id)

    def test_exact_utf8_byte_limit_is_allowed(self):
        text = "<r>" + "я" * 28 + "x</r>"
        self.manager.max_file_bytes = len(text.encode("utf-8"))
        self.manager.write_xml("boundary.xml", text, self.user_id)
        self.assertEqual(self.manager.read_xml("boundary.xml", self.user_id).text, "я" * 28 + "x")

    def test_malformed_xml_does_not_modify_existing_file_or_metadata(self):
        self.manager.write_xml("existing.xml", "<r>old</r>", self.user_id)
        before = list(self.audit._connection.execute("SELECT * FROM Files"))
        for text in ("", "<root>", "<root>&undefined;</root>"):
            with self.subTest(text=text), self.assertRaisesRegex(SafeFileError, "Некорректный XML"):
                self.manager.write_xml("existing.xml", text, self.user_id)
        self.assertEqual((self.manager.root / "existing.xml").read_text(encoding="utf-8"), "<r>old</r>")
        self.assertEqual(list(self.audit._connection.execute("SELECT * FROM Files")), before)

    def test_cli_xml_rejections_are_logged_without_payload(self):
        text = '<!DOCTYPE root [<!ENTITY e "private-payload">]><root>&e;</root>'
        self.manager.write_text("raw.xml", text, self.user_id)
        for command, arguments in (
            ("xml-write", ["bad.xml", "--value", text]),
            ("xml-read", ["raw.xml"]),
        ):
            with self.subTest(command=command), \
                    patch.object(app, "DATA_ROOT", self.manager.root), \
                    patch.object(app, "AUDIT_DATABASE", self.database), \
                    patch("lab1.src.app.getpass.getpass", return_value=self.password), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(app.run([command, *arguments, "--user", "demo"]), 2)
                row = self.audit._connection.execute(
                    "SELECT operation_type, detail FROM Operations ORDER BY id DESC LIMIT 1"
                ).fetchone()
                self.assertEqual(row[0], command + "_failed")
                self.assertIn("DTD", row[1])
                self.assertNotIn("private-payload", row[1])
                self.assertNotIn(self.password, row[1])

    def test_xml_refuses_outdated_expat(self):
        for version in ((2, 6, 3), (2, 7, 1)):
            with self.subTest(version=version), patch("pyexpat.version_info", version):
                with self.assertRaisesRegex(SafeFileError, "Expat 2.7.2"):
                    self.manager.write_xml("blocked.xml", "<root/>", self.user_id)
        self.assertFalse((self.manager.root / "blocked.xml").exists())
