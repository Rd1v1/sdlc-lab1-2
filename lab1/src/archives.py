"""Безопасное создание ZIP и проверка всех записей перед распаковкой."""
from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from .errors import SafeFileError


def create_zip(manager, archive_name: str, names: list[str], user_id: int) -> None:
    if not names:
        raise SafeFileError("Нужно выбрать хотя бы один файл")
    archive_path = manager._path(archive_name)
    if archive_path.exists():
        raise SafeFileError("Архив уже существует; перезапись запрещена")
    sources = [(manager._path(name), name) for name in names]
    if any(not path.is_file() for path, _ in sources):
        raise SafeFileError("Один из файлов для архивации не найден")
    for path, _ in sources:
        manager.audit.ensure_owner(path.relative_to(manager.root).as_posix(), user_id, require_registered=True)
    manager.audit.ensure_owner(
        archive_path.relative_to(manager.root).as_posix(), user_id, require_registered=archive_path.exists()
    )
    total = sum(path.stat().st_size for path, _ in sources)
    if total > manager.max_archive_bytes:
        raise SafeFileError("Суммарный размер архива превышает лимит")
    with manager.audit.transaction():
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=archive_path.parent, suffix=".zip", delete=False) as temporary:
            temporary_path = Path(temporary.name)
        try:
            with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path, name in sources:
                    archive.write(path, arcname=path.relative_to(manager.root).as_posix())
            if temporary_path.stat().st_size > manager.max_file_bytes:
                raise SafeFileError("Размер ZIP-файла превышает лимит")
            os.replace(temporary_path, archive_path)
            manager.audit.record_file(archive_path.relative_to(manager.root).as_posix(), archive_path.stat().st_size, user_id, "write")
        finally:
            temporary_path.unlink(missing_ok=True)


def extract_zip(manager, archive_name: str, destination: str, user_id: int) -> list[str]:
    archive_path = manager._path(archive_name)
    destination_path = manager._path(destination)
    if not archive_path.is_file():
        raise SafeFileError("ZIP-архив не найден")
    if archive_path.stat().st_size > manager.max_file_bytes:
        raise SafeFileError("ZIP-файл превышает установленный лимит")
    manager.audit.ensure_owner(archive_path.relative_to(manager.root).as_posix(), user_id, require_registered=True)
    with manager.audit.transaction(), zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        if len(entries) > 1000:
            raise SafeFileError("В архиве слишком много записей")
        total_size = sum(entry.file_size for entry in entries)
        if total_size > manager.max_archive_bytes:
            raise SafeFileError("Распакованный архив превышает лимит")
        for entry in entries:
            member = PurePosixPath(entry.filename)
            windows_member = PureWindowsPath(entry.filename)
            mode = entry.external_attr >> 16
            if (
                member.is_absolute()
                or windows_member.is_absolute()
                or ".." in member.parts
                or ".." in windows_member.parts
                or "\\" in entry.filename
                or ":" in entry.filename
                or (mode & 0o170000) == 0o120000
            ):
                raise SafeFileError("Архив содержит небезопасный путь или ссылку")
            if entry.file_size > 0 and entry.compress_size == 0:
                raise SafeFileError("Недопустимая степень сжатия")
            if entry.file_size > manager.max_file_bytes:
                raise SafeFileError("Один из файлов архива превышает лимит размера")
            ratio = entry.file_size / max(entry.compress_size, 1)
            if ratio > manager.max_compression_ratio:
                raise SafeFileError("Степень сжатия превышает допустимый предел")
        # Validate every target before any extraction and never overwrite existing data.
        targets = {}
        for entry in entries:
            output = manager._path((Path(destination) / entry.filename).as_posix())
            key = os.path.normcase(str(output))
            if key in targets or output.exists():
                raise SafeFileError("Цель ZIP уже существует или повторяется; перезапись запрещена")
            targets[key] = entry.is_dir()
        # A file named 'a' cannot also be the parent of 'a/b'. Reject the
        # entire conflicting layout before writing the first member.
        for entry in entries:
            output = manager._path((Path(destination) / entry.filename).as_posix())
            for parent in output.parents:
                if parent == manager.root:
                    break
                parent_key = os.path.normcase(str(parent))
                if parent.is_file() or (parent_key in targets and not targets[parent_key]):
                    raise SafeFileError("Файл ZIP конфликтует с каталогом назначения")
        destination_path.mkdir(parents=True, exist_ok=True)
        extracted = []
        for entry in entries:
            if entry.is_dir():
                manager._path((Path(destination) / entry.filename).as_posix()).mkdir(parents=True, exist_ok=True)
                continue
            output = (destination_path / Path(*PurePosixPath(entry.filename).parts)).resolve()
            if not output.is_relative_to(destination_path.resolve()):
                raise SafeFileError("Путь из архива выходит за каталог назначения")
            relative = output.relative_to(manager.root).as_posix()
            manager.audit.ensure_owner(relative, user_id)
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = None
            try:
                with archive.open(entry) as source, tempfile.NamedTemporaryFile(
                    dir=output.parent, delete=False
                ) as temporary:
                    temporary_path = Path(temporary.name)
                    shutil.copyfileobj(source, temporary, length=64 * 1024)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temporary_path, output)
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
            manager.audit.record_file(relative, output.stat().st_size, user_id, "write")
            extracted.append(relative)
        return extracted
