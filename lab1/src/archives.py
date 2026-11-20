from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from .errors import SafeFileError
from .file_changes import atomic_writer


def create_zip(manager, archive_name: str, names: list[str], user_id: int) -> None:
    if not names:
        raise SafeFileError("Нужно выбрать хотя бы один файл")
    archive_path = manager._path(archive_name)
    if archive_path.exists():
        raise SafeFileError("Архив уже существует; перезапись запрещена")
    sources = [manager._path(name) for name in names]
    if any(not path.is_file() for path in sources):
        raise SafeFileError("Один из файлов для архивации не найден")
    for path in sources:
        manager.audit.ensure_owner(path.relative_to(manager.root).as_posix(), user_id, require_registered=True)
    manager.audit.ensure_owner(
        archive_path.relative_to(manager.root).as_posix(), user_id, require_registered=archive_path.exists()
    )
    total = sum(path.stat().st_size for path in sources)
    if total > manager.max_archive_bytes:
        raise SafeFileError("Суммарный размер архива превышает лимит")
    with manager.audit.transaction() as changes:
        changes.mkdir(archive_path.parent)
        changes.preserve_file(archive_path)
        with atomic_writer(archive_path) as temporary:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sources:
                    archive.write(path, arcname=path.relative_to(manager.root).as_posix())
            if temporary.tell() > manager.max_file_bytes:
                raise SafeFileError("Размер ZIP-файла превышает лимит")
        manager.audit.record_file(archive_path.relative_to(manager.root).as_posix(), archive_path.stat().st_size, user_id, "write")


def extract_zip(manager, archive_name: str, destination: str, user_id: int) -> list[str]:
    archive_path = manager._path(archive_name)
    destination_path = manager._path(destination)
    if not archive_path.is_file():
        raise SafeFileError("ZIP-архив не найден")
    if archive_path.stat().st_size > manager.max_file_bytes:
        raise SafeFileError("ZIP-файл превышает установленный лимит")
    manager.audit.ensure_owner(archive_path.relative_to(manager.root).as_posix(), user_id, require_registered=True)
    with manager.audit.transaction() as changes, zipfile.ZipFile(archive_path) as archive:
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
        targets = {}
        for entry in entries:
            output = manager._path((Path(destination) / entry.filename).as_posix())
            key = os.path.normcase(str(output))
            if key in targets or output.exists():
                raise SafeFileError("Цель ZIP уже существует или повторяется; перезапись запрещена")
            targets[key] = entry.is_dir()
        for entry in entries:
            output = manager._path((Path(destination) / entry.filename).as_posix())
            for parent in output.parents:
                if parent == manager.root:
                    break
                parent_key = os.path.normcase(str(parent))
                if parent.is_file() or (parent_key in targets and not targets[parent_key]):
                    raise SafeFileError("Файл ZIP конфликтует с каталогом назначения")
        changes.mkdir(destination_path)
        extracted = []
        for entry in entries:
            if entry.is_dir():
                changes.mkdir(manager._path((Path(destination) / entry.filename).as_posix()))
                continue
            output = (destination_path / Path(*PurePosixPath(entry.filename).parts)).resolve()
            if not output.is_relative_to(destination_path.resolve()):
                raise SafeFileError("Путь из архива выходит за каталог назначения")
            relative = output.relative_to(manager.root).as_posix()
            manager.audit.ensure_owner(relative, user_id)
            changes.mkdir(output.parent)
            changes.preserve_file(output)
            with archive.open(entry) as source, atomic_writer(output) as temporary:
                shutil.copyfileobj(source, temporary, length=64 * 1024)
            manager.audit.record_file(relative, output.stat().st_size, user_id, "write")
            extracted.append(relative)
        return extracted
