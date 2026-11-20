import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from defusedxml import ElementTree as SafeET
from pypdf import PdfReader

from scripts.security_reports import export_reports, main


BANDIT = {
    "errors": [], "generated_at": "2026-11-07T00:00:00Z",
    "metrics": {"_totals": {"SEVERITY.HIGH": 0, "SEVERITY.MEDIUM": 0, "SEVERITY.LOW": 2}},
    "results": [],
}


def xml_data(node):
    kind = node.get("type")
    if kind == "object":
        return {child.get("name"): xml_data(child) for child in node}
    if kind == "array":
        return [xml_data(child) for child in node]
    if kind == "string":
        return node.text or ""
    if kind == "null":
        return None
    return json.loads(node.text)


class SecurityReportsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def export(self, tool, data):
        source = self.root / (tool + ".json")
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        source.write_bytes(raw)
        xml, pdf = export_reports(tool, source)
        self.assertEqual(source.read_bytes(), raw)
        tree = SafeET.parse(xml, forbid_dtd=True, forbid_entities=True, forbid_external=True).getroot()
        self.assertEqual(tree.get("tool"), tool)
        self.assertEqual(tree.find("source").get("sha256"), hashlib.sha256(raw).hexdigest())
        self.assertEqual(xml_data(tree.find("analyzer-report")), data)
        reader = PdfReader(pdf)
        self.assertGreaterEqual(len(reader.pages), 1)
        text = "\n".join(page.extract_text() for page in reader.pages)
        self.assertIn("Отчёт безопасности", text)
        self.assertIn(hashlib.sha256(raw).hexdigest(), text.replace("\n", ""))
        return tree, reader, text

    def test_bandit_findings_preserve_cyrillic_code_and_literal_markup(self):
        data = copy.deepcopy(BANDIT)
        data["metrics"]["_totals"]["SEVERITY.HIGH"] = 1
        text = '<img src="missing.png"/> & <b>пример</b>'
        data["results"] = [{
            "filename": "каталог/файл.py", "line_number": 7, "line_range": [7, 8],
            "issue_severity": "HIGH", "issue_confidence": "HIGH", "test_id": "B999",
            "test_name": "example", "issue_text": text, "code": "7 " + text,
            "issue_cwe": {"id": 78, "link": "https://example.invalid/cwe/78"},
            "more_info": "https://example.invalid/?a=1&b=2",
        }]
        _, _, pdf_text = self.export("bandit", data)
        for expected in ("каталог/файл.py", text, "B999", "HIGH"):
            self.assertIn(expected, pdf_text)

    def test_sca_vulnerabilities_fixes_aliases_and_skips_are_visible(self):
        data = {"dependencies": [
            {"name": "example-package", "version": "1.0", "vulns": [{
                "id": "EXAMPLE-2026-1", "fix_versions": ["1.1", "2.0"],
                "aliases": ["CVE-EXAMPLE"], "description": "Описание <ошибки> & защиты",
            }]},
            {"name": "local-package", "version": "0.1", "skip_reason": "Пакет не найден"},
        ], "fixes": [], "extra/key": {"enabled": True, "missing": None, "weights": [1, 1.5]}}
        tree, _, text = self.export("pip-audit", data)
        self.assertEqual(tree.find("summary/metric[@name='skipped']").get("value"), "1")
        for expected in ("EXAMPLE-2026-1", "CVE-EXAMPLE", "1.1, 2.0", "Пакет не найден", "Описание <ошибки> & защиты"):
            self.assertIn(expected, text)

    def test_filtered_bandit_summary_does_not_hide_lower_severity_metrics(self):
        tree, _, text = self.export("bandit", copy.deepcopy(BANDIT))
        self.assertEqual(tree.find("summary/metric[@name='low']").get("value"), "2")
        self.assertEqual(tree.find("summary/metric[@name='listed_findings']").get("value"), "0")
        self.assertIn("В CI установлен порог High", text)

    def test_dependency_table_spans_pages_without_losing_last_package(self):
        for count in (34, 90):
            with self.subTest(count=count):
                data = {"dependencies": [{"name": f"package-{i:03}", "version": "1.0", "vulns": []} for i in range(count)]}
                _, reader, text = self.export("pip-audit", data)
                self.assertGreater(len(reader.pages), 1)
                self.assertIn("package-000", reader.pages[0].extract_text())
                self.assertIn(f"package-{count-1:03}", text)

    def test_long_finding_and_source_code_span_pages(self):
        data = copy.deepcopy(BANDIT)
        data["results"] = [{"test_id": "B999", "issue_text": "START\n" + "Строка описания\n" * 80 + "END-DESCRIPTION",
                            "code": "Исходный код\n" * 80 + "END-CODE"}]
        data["errors"] = [{"filename": "bad.py", "reason": "Ошибка разбора"}]
        _, reader, text = self.export("bandit", data)
        self.assertGreater(len(reader.pages), 1)
        for expected in ("START", "END-DESCRIPTION", "END-CODE", "Ошибка разбора"):
            self.assertIn(expected, text)

    def test_invalid_or_missing_json_cannot_create_success_reports(self):
        source = self.root / "bad.json"
        cases = [("bandit", "{"), ("bandit", "{}"), ("pip-audit", "[]"),
                 ("pip-audit", '{"dependencies":[{"name":"unknown"}]}')]
        for tool, raw in cases:
            source.write_text(raw, encoding="utf-8")
            with self.subTest(tool=tool, raw=raw), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main([tool, str(source)]), 2)
                self.assertFalse(source.with_suffix(".pdf").exists())
                self.assertFalse(source.with_suffix(".xml").exists())
        source.unlink()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["bandit", str(source)]), 2)

    def test_non_json_extension_cannot_overwrite_source(self):
        source = self.root / "report.xml"
        original = json.dumps(BANDIT)
        source.write_text(original, encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["bandit", str(source)]), 2)
        self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_pdf_write_failure_is_an_export_failure(self):
        source = self.root / "bandit.json"
        source.write_text(json.dumps(BANDIT), encoding="utf-8")
        with patch("scripts.security_reports._pdf", side_effect=PermissionError("denied")), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["bandit", str(source)]), 2)
        self.assertFalse(source.with_suffix(".xml").exists())
