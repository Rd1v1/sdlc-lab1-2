"""Файловые операции и координация проверок, блокировок и аудита."""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
from .archives import create_zip, extract_zip
from .audit import AuditStore
from .drives import list_drives
from .errors import SafeFileError
from .paths import resolve_path


class SafeFileManager:
    def __init__(
        self,
        root: Path,
        audit: AuditStore,
        max_file_bytes: int = 1_048_576,
        max_archive_bytes: int = 10_485_760,
        max_compression_ratio: float = 100.0,
    ):
        if max_file_bytes <= 0 or max_archive_bytes <= 0 or max_compression_ratio < 1:
            raise ValueError("Лимиты должны быть положительными")
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.audit = audit
        self.max_file_bytes = max_file_bytes
        self.max_archive_bytes = max_archive_bytes
        self.max_compression_ratio = max_compression_ratio

    def list_files(self, user_id: int) -> list[dict[str, Any]]:
        return self.audit.list_owned_files(user_id)

    def read_text(self, name: str, user_id: int) -> str:
        path = self._path(name)
        with self.audit.transaction():
            if not path.is_file():
                raise SafeFileError("Файл не найден")
            self.audit.ensure_owner(path.relative_to(self.root).as_posix(), user_id, require_registered=True)
            if path.stat().st_size > self.max_file_bytes:
                raise SafeFileError("Файл превышает установленный лимит")
            content = path.read_text(encoding="utf-8")
            self.audit.record_activity("read", path.relative_to(self.root).as_posix(), user_id)
            return content

    def write_bytes(self, name: str, data: bytes, user_id: int) -> None:
        if len(data) > self.max_file_bytes:
            raise SafeFileError("Размер файла превышает установленный лимит")
        path = self._path(name)
        with self.audit.transaction():
            self.audit.ensure_owner(
                path.relative_to(self.root).as_posix(), user_id, require_registered=path.exists()
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
                    temporary_path = Path(temporary.name)
                    temporary.write(data)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temporary_path, path)
                self.audit.record_file(path.relative_to(self.root).as_posix(), len(data), user_id, "write")
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)

    def write_text(self, name: str, text: str, user_id: int) -> None:
        self.write_bytes(name, text.encode("utf-8"), user_id)

    def delete(self, name: str, user_id: int) -> None:
        path = self._path(name)
        with self.audit.transaction():
            if not path.is_file():
                raise SafeFileError("Файл не найден")
            self.audit.ensure_owner(path.relative_to(self.root).as_posix(), user_id, require_registered=True)
            path.unlink()
            self.audit.record_file(path.relative_to(self.root).as_posix(), 0, user_id, "delete")

    def write_json(self, name: str, value: Any, user_id: int) -> None:
        self.write_text(name, json.dumps(value, ensure_ascii=False, indent=2), user_id)

    def read_json(self, name: str, user_id: int) -> Any:
        return json.loads(self.read_text(name, user_id))

    def write_xml(self, name: str, xml_text: str, user_id: int) -> None:
        self._parse_xml(xml_text)
        self.write_text(name, xml_text, user_id)

    def read_xml(self, name: str, user_id: int) -> ET.Element:
        return self._parse_xml(self.read_text(name, user_id))

    @staticmethod
    def _parse_xml(xml_text: str) -> ET.Element:
        if re.search(r"<!\s*(DOCTYPE|ENTITY)", xml_text, flags=re.IGNORECASE):
            raise SafeFileError("DTD и объявления сущностей в XML запрещены")
        try:
            return ET.fromstring(xml_text)
        except ET.ParseError as error:
            raise SafeFileError("Некорректный XML") from error

    def create_zip(self, archive_name: str, names: list[str], user_id: int) -> None:
        with self.audit.transaction():
            create_zip(self, archive_name, names, user_id)

    def extract_zip(self, archive_name: str, destination: str, user_id: int) -> list[str]:
        with self.audit.transaction():
            return extract_zip(self, archive_name, destination, user_id)

    def _path(self, name: str) -> Path:
        return resolve_path(self.root, name)

    @staticmethod
    def list_drives():
        return list_drives()
