"""Export existing Bandit/pip-audit JSON reports to XML and a readable PDF."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from defusedxml import ElementTree as SafeET
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer


TOOLS = {"bandit": "Bandit / SAST", "pip-audit": "pip-audit / SCA"}


def _summary(tool, data):
    if not isinstance(data, dict):
        raise ValueError("Expected an analyzer JSON object")
    if tool == "bandit":
        if not isinstance(data.get("results"), list) or not isinstance(data.get("errors"), list):
            raise ValueError("Invalid Bandit results/errors")
        totals = data.get("metrics", {}).get("_totals")
        if not isinstance(totals, dict) or not all(isinstance(item, dict) for item in data["results"]):
            raise ValueError("Invalid Bandit metrics/findings")
        return {
            **{level.lower(): totals[f"SEVERITY.{level}"] for level in ("HIGH", "MEDIUM", "LOW")},
            "listed_findings": len(data["results"]), "errors": len(data["errors"]),
        }
    dependencies = data.get("dependencies")
    if not isinstance(dependencies, list):
        raise ValueError("Invalid pip-audit dependencies")
    for item in dependencies:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ValueError("Invalid pip-audit dependency")
        if not isinstance(item.get("vulns"), list) and not isinstance(item.get("skip_reason"), str):
            raise ValueError("Dependency has neither vulnerabilities nor a skip reason")
        if not all(isinstance(vuln, dict) for vuln in item.get("vulns", [])):
            raise ValueError("Invalid pip-audit vulnerability")
    return {
        "dependencies": len(dependencies),
        "vulnerabilities": sum(len(item.get("vulns", [])) for item in dependencies),
        "skipped": sum("skip_reason" in item for item in dependencies),
    }


def _xml_value(node, value):
    """Fixed XML tag names also support JSON keys that are paths or contain spaces."""
    if isinstance(value, dict):
        node.set("type", "object")
        for key, item in value.items():
            _xml_value(ET.SubElement(node, "field", name=key), item)
    elif isinstance(value, list):
        node.set("type", "array")
        for item in value:
            _xml_value(ET.SubElement(node, "item"), item)
    elif value is None:
        node.set("type", "null")
    elif isinstance(value, str):
        node.set("type", "string")
        node.text = value
    else:
        node.set("type", "boolean" if isinstance(value, bool) else "number")
        node.text = json.dumps(value, allow_nan=False)


def _pdf(path, report):
    fonts = Path(__file__).with_name("fonts")
    for name, filename in (("AuditSans", "DejaVuSans.ttf"), ("AuditBold", "DejaVuSans-Bold.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(fonts / filename)))
    body = ParagraphStyle("Body", fontName="AuditSans", fontSize=9, leading=13, spaceAfter=6)
    small = ParagraphStyle("Small", parent=body, fontSize=8, leading=11, textColor=colors.HexColor("#475569"))
    heading = ParagraphStyle("Heading", parent=body, fontName="AuditBold", fontSize=12, leading=16,
                             spaceBefore=12, spaceAfter=7, keepWithNext=True)
    table_heading = ParagraphStyle("TableHeading", parent=heading, keepWithNext=False)
    title = ParagraphStyle("Title", parent=heading, fontSize=21, leading=27, spaceBefore=0)
    story = []

    def paragraph(value, style=body):
        # Analyzer messages and source code are data, never ReportLab markup or image URLs.
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)

    def add(value, style=body):
        story.append(paragraph(value, style))

    def table(headers, rows, widths):
        content = [[paragraph(value, small) for value in row] for row in [headers, *rows]]
        result = LongTable(content, colWidths=widths, repeatRows=1, hAlign="LEFT")
        result.setStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.HexColor("#94a3b8")),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
        story.extend([result, Spacer(1, 8)])

    add("Отчёт безопасности", title)
    add("LAB 2 | " + TOOLS[report["tool"]], heading)
    add("Сформирован (UTC): " + report["generated_at"], small)
    add("Исходный JSON: " + report["source"], small)
    add("SHA-256: " + report["sha256"], small)
    labels = {"high": "High", "medium": "Medium", "low": "Low", "listed_findings": "Находки в JSON",
              "errors": "Ошибки анализа", "dependencies": "Проверяемые пакеты",
              "vulnerabilities": "Известные уязвимости", "skipped": "Пропущенные пакеты"}
    table(["Показатель", "Количество"], [[labels[key], value] for key, value in report["summary"].items()], [365, 150])
    data = report["data"]
    if report["tool"] == "bandit":
        add("Подробные находки", heading)
        add("В CI установлен порог High. Подробности берутся из исходного JSON; сводные метрики могут включать находки других уровней.", small)
        if not data["results"]:
            add("Находки, включённые в исходный JSON, отсутствуют.")
        for index, item in enumerate(data["results"], 1):
            add(f'{index}. {item.get("test_id", "")} / {item.get("test_name", "")}', heading)
            add(f'{item.get("filename", "")} : {item.get("line_number", "")} | {item.get("issue_severity", "")} | confidence: {item.get("issue_confidence", "")}')
            add(item.get("issue_text", ""))
            if item.get("issue_cwe"):
                add("CWE: " + json.dumps(item["issue_cwe"], ensure_ascii=False), small)
            if item.get("more_info"):
                add(item["more_info"], small)
            if item.get("code"):
                add("Код:", small)
                add(item["code"], small)
        if data["errors"]:
            add("Ошибки и пропуски анализа", heading)
            for error in data["errors"]:
                add(json.dumps(error, ensure_ascii=False))
    else:
        add("Зависимости", table_heading)
        dependencies = data["dependencies"]
        table(["Пакет", "Версия", "Уязвимости", "Пропуск"], [
            [item["name"], item.get("version", "-"), len(item.get("vulns", [])), "Да" if "skip_reason" in item else "-"]
            for item in dependencies
        ], [220, 95, 100, 100])
        for item in dependencies:
            if "skip_reason" in item:
                add("Пропуск: " + item["name"], heading)
                add(item["skip_reason"])
            for vuln in item.get("vulns", []):
                add(f'{item["name"]} {item.get("version", "")} / {vuln.get("id", "")}', heading)
                add("Исправлено в версиях: " + (", ".join(vuln.get("fix_versions", [])) or "не указано"))
                if vuln.get("aliases"):
                    add("Другие идентификаторы: " + ", ".join(vuln["aliases"]), small)
                if vuln.get("description"):
                    add(vuln["description"])

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("AuditSans", 8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(40, 23, "LAB 2 | " + TOOLS[report["tool"]])
        canvas.drawRightString(A4[0] - 40, 23, str(document.page))
        canvas.restoreState()

    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=40, rightMargin=40, topMargin=36,
                      bottomMargin=40, title=TOOLS[report["tool"]] + " security report",
                      author="LAB 2").build(story, onFirstPage=footer, onLaterPages=footer)


def export_reports(tool: str, source: Path) -> tuple[Path, Path]:
    if source.suffix.lower() != ".json":
        raise ValueError("Expected a .json source file")
    raw = source.read_bytes()
    data = json.loads(raw)
    report = {"tool": tool, "data": data, "summary": _summary(tool, data), "source": source.name,
              "sha256": hashlib.sha256(raw).hexdigest(),
              "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    root = ET.Element("security-report", tool=tool, version="1", generated_at=report["generated_at"])
    ET.SubElement(root, "source", name=source.name, sha256=report["sha256"])
    summary = ET.SubElement(root, "summary")
    for name, value in report["summary"].items():
        ET.SubElement(summary, "metric", name=name, value=str(value))
    _xml_value(ET.SubElement(root, "analyzer-report"), data)
    ET.indent(root)
    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    SafeET.fromstring(xml, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    xml_path, pdf_path = source.with_suffix(".xml"), source.with_suffix(".pdf")
    _pdf(pdf_path, report)
    xml_path.write_bytes(xml)
    return xml_path, pdf_path


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", choices=TOOLS)
    parser.add_argument("source", type=Path, help="Existing analyzer JSON report")
    options = parser.parse_args(arguments)
    try:
        for output in export_reports(options.tool, options.source):
            print(output)
        return 0
    except Exception as error:
        print(f"Report export failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
