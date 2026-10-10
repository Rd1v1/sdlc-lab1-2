from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import tempfile
import threading
import zipfile
import ctypes
import contextlib
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
import xml.etree.ElementTree as ET


class SafeFileError(ValueError):
    """Raised when an operation violates a file-manager security limit."""


class AuditStore:
    def __init__(self, database: Path):
        database.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock, self._connection:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS Users (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS Files (
                    id INTEGER PRIMARY KEY,
                    filename TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    size INTEGER NOT NULL CHECK (size >= 0),
                    location TEXT NOT NULL UNIQUE,
                    owner_id INTEGER NOT NULL REFERENCES Users(id)
                );
                CREATE TABLE IF NOT EXISTS Operations (
                    id INTEGER PRIMARY KEY,
                    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    operation_type TEXT NOT NULL,
                    file_id INTEGER REFERENCES Files(id) ON DELETE SET NULL,
                    user_id INTEGER REFERENCES Users(id),
                    detail TEXT NOT NULL DEFAULT ''
                );
                """
            )

    def create_user(self, username: str, password: str) -> int:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,50}", username):
            raise SafeFileError("Логин: 1-50 символов, допустимы буквы, цифры, . _ -")
        if len(password) < 8 or len(password) > 1024:
            raise SafeFileError("Пароль должен содержать от 8 до 1024 символов")
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
        try:
            with self._lock, self._connection:
                cursor = self._connection.execute(
                    "INSERT INTO Users(username, password_salt, password_hash) VALUES (?, ?, ?)",
                    (username, salt, digest),
                )
                user_id = int(cursor.lastrowid)
                self._connection.execute(
                    "INSERT INTO Operations(operation_type, user_id, detail) VALUES (?, ?, ?)",
                    ("register", user_id, username),
                )
                return user_id
        except sqlite3.IntegrityError as error:
            raise SafeFileError("Пользователь с таким логином уже существует") from error

    def authenticate(self, username: str, password: str) -> int | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT id, password_salt, password_hash FROM Users WHERE username = ?",
                (username,),
            ).fetchone()
        if row is None:
            with self._lock, self._connection:
                self._connection.execute(
                    "INSERT INTO Operations(operation_type, detail) VALUES (?, ?)",
                    ("login_failed", username[:50]),
                )
            return None
        candidate = hashlib.scrypt(
            password.encode("utf-8"), salt=row["password_salt"], n=2**14, r=8, p=1
        )
        user_id = int(row["id"])
        success = hmac.compare_digest(candidate, row["password_hash"])
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO Operations(operation_type, user_id, detail) VALUES (?, ?, ?)",
                ("login" if success else "login_failed", user_id, username),
            )
        return user_id if success else None

    def record_file(self, path: str, size: int, user_id: int, operation: str) -> None:
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT id FROM Files WHERE location = ?", (path,)
            ).fetchone()
            if operation == "delete":
                file_id = int(row["id"]) if row else None
                self._connection.execute(
                    "INSERT INTO Operations(operation_type, file_id, user_id, detail) "
                    "VALUES (?, ?, ?, ?)",
                    (operation, file_id, user_id, path),
                )
                self._connection.execute("DELETE FROM Files WHERE location = ?", (path,))
                return
            if row:
                file_id = int(row["id"])
                self._connection.execute(
                    "UPDATE Files SET filename = ?, size = ?, owner_id = ? WHERE id = ?",
                    (Path(path).name, size, user_id, file_id),
                )
                operation = "modify"
            else:
                cursor = self._connection.execute(
                    "INSERT INTO Files(filename, size, location, owner_id) VALUES (?, ?, ?, ?)",
                    (Path(path).name, size, path, user_id),
                )
                file_id = int(cursor.lastrowid)
                operation = "create"
            self._connection.execute(
                "INSERT INTO Operations(operation_type, file_id, user_id, detail) "
                "VALUES (?, ?, ?, ?)",
                (operation, file_id, user_id, path),
            )

    def record_activity(self, operation: str, path: str, user_id: int) -> None:
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT id FROM Files WHERE location = ?", (path,)
            ).fetchone()
            self._connection.execute(
                "INSERT INTO Operations(operation_type, file_id, user_id, detail) "
                "VALUES (?, ?, ?, ?)",
                (operation, int(row["id"]) if row else None, user_id, path),
            )

    def ensure_owner(self, path: str, user_id: int, require_registered: bool = False) -> None:
        with self._lock:
            row = self._connection.execute(
                "SELECT owner_id FROM Files WHERE location = ?", (path,)
            ).fetchone()
        if row is None and require_registered:
            raise SafeFileError("Файл не зарегистрирован в хранилище приложения")
        if row is not None and int(row["owner_id"]) != user_id:
            raise SafeFileError("Нет доступа к файлу другого пользователя")

    def list_owned_files(self, user_id: int) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT filename, location, size, created_at FROM Files WHERE owner_id = ? ORDER BY location",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._connection.close()


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
        self._lock = threading.RLock()
        self._process_lock_state = threading.local()

    @contextlib.contextmanager
    def _cross_process_lock(self):
        depth = getattr(self._process_lock_state, "depth", 0)
        if depth:
            self._process_lock_state.depth = depth + 1
            try:
                yield
            finally:
                self._process_lock_state.depth -= 1
            return

        if os.name == "nt":
            kernel = ctypes.windll.kernel32
            handle_type = ctypes.c_void_p
            kernel.CreateMutexW.argtypes = (handle_type, ctypes.c_bool, ctypes.c_wchar_p)
            kernel.CreateMutexW.restype = handle_type
            kernel.WaitForSingleObject.argtypes = (handle_type, ctypes.c_uint32)
            kernel.WaitForSingleObject.restype = ctypes.c_uint32
            kernel.ReleaseMutex.argtypes = (handle_type,)
            kernel.CloseHandle.argtypes = (handle_type,)
            key = hashlib.sha256(os.path.normcase(str(self.root)).encode("utf-8")).hexdigest()
            mutex = kernel.CreateMutexW(None, False, f"Local\\Lab1FileManager_{key}")
            if not mutex:
                raise OSError("Не удалось создать межпроцессную блокировку")
            wait_result = kernel.WaitForSingleObject(mutex, 0xFFFFFFFF)
            if wait_result not in (0, 0x80):
                kernel.CloseHandle(mutex)
                raise OSError("Не удалось получить межпроцессную блокировку")
            self._process_lock_state.depth = 1
            try:
                yield
            finally:
                self._process_lock_state.depth = 0
                kernel.ReleaseMutex(mutex)
                kernel.CloseHandle(mutex)
            return

        import fcntl

        lock_path = self.root.parent / f".{self.root.name}.lock"
        with lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            self._process_lock_state.depth = 1
            try:
                yield
            finally:
                self._process_lock_state.depth = 0
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _path(self, name: str) -> Path:
        if not name or "\x00" in name:
            raise SafeFileError("Имя файла не должно быть пустым")
        # Reject drive-relative paths, NTFS alternate streams and ambiguous Windows names.
        windows = PureWindowsPath(name)
        if windows.drive or windows.root or ":" in name:
            raise SafeFileError("Путь с диском или потоком NTFS запрещён")
        if any(part.endswith((" ", ".")) and part not in (".", "..") for part in windows.parts):
            raise SafeFileError("Имя не должно оканчиваться пробелом или точкой")
        if any(re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part) for part in windows.parts):
            raise SafeFileError("Системное имя устройства запрещено")
        if Path(name).is_absolute() or PureWindowsPath(name).is_absolute():
            raise SafeFileError("Абсолютные пути запрещены")
        candidate = (self.root / name).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as error:
            raise SafeFileError("Путь выходит за пределы рабочего каталога") from error
        if candidate == self.root:
            raise SafeFileError("Ожидалось имя файла внутри рабочего каталога")
        # Local users must not be able to substitute symlinks/junctions inside the store.
        unresolved = self.root / name
        for part in (unresolved, *unresolved.parents):
            if part == self.root:
                break
            if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
                raise SafeFileError("Символические ссылки и junction запрещены")
        return candidate

    def list_files(self, user_id: int) -> list[dict[str, Any]]:
        return self.audit.list_owned_files(user_id)

    def read_text(self, name: str, user_id: int) -> str:
        path = self._path(name)
        with self._lock, self._cross_process_lock():
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
        with self._lock, self._cross_process_lock():
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
        with self._lock, self._cross_process_lock():
            if not path.is_file():
                raise SafeFileError("Файл не найден")
            self.audit.ensure_owner(path.relative_to(self.root).as_posix(), user_id, require_registered=True)
            path.unlink()
            self.audit.record_file(path.relative_to(self.root).as_posix(), 0, user_id, "delete")

    def copy_file(self, source_name: str, destination_name: str, user_id: int) -> None:
        source = self._path(source_name)
        destination = self._path(destination_name)
        with self._lock, self._cross_process_lock():
            if not source.is_file():
                raise SafeFileError("Исходный файл не найден")
            source_key = source.relative_to(self.root).as_posix()
            destination_key = destination.relative_to(self.root).as_posix()
            self.audit.ensure_owner(source_key, user_id, require_registered=True)
            self.audit.ensure_owner(destination_key, user_id)
            if destination.exists():
                raise SafeFileError("Файл назначения уже существует; перезапись запрещена")
            if source.stat().st_size > self.max_file_bytes:
                raise SafeFileError("Исходный файл превышает установленный лимит")
            data = source.read_bytes()
            self.write_bytes(destination_name, data, user_id)
            self.audit.record_activity("copy", source_key, user_id)

    def move_file(self, source_name: str, destination_name: str, user_id: int) -> None:
        source = self._path(source_name)
        destination = self._path(destination_name)
        with self._lock, self._cross_process_lock():
            if not source.is_file():
                raise SafeFileError("Исходный файл не найден")
            source_key = source.relative_to(self.root).as_posix()
            destination_key = destination.relative_to(self.root).as_posix()
            self.audit.ensure_owner(source_key, user_id, require_registered=True)
            self.audit.ensure_owner(destination_key, user_id)
            if destination.exists():
                raise SafeFileError("Файл назначения уже существует; перезапись запрещена")
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(source, destination)
            except OSError as error:
                raise SafeFileError("Не удалось атомарно создать файл назначения") from error
            source.unlink()
            self.audit.record_file(destination_key, destination.stat().st_size, user_id, "write")
            self.audit.record_file(source_key, 0, user_id, "delete")

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
        with self._lock, self._cross_process_lock():
            self._create_zip_locked(archive_name, names, user_id)

    def _create_zip_locked(self, archive_name: str, names: list[str], user_id: int) -> None:
        if not names:
            raise SafeFileError("Нужно выбрать хотя бы один файл")
        archive_path = self._path(archive_name)
        if archive_path.exists():
            raise SafeFileError("Архив уже существует; перезапись запрещена")
        sources = [(self._path(name), name) for name in names]
        if any(not path.is_file() for path, _ in sources):
            raise SafeFileError("Один из файлов для архивации не найден")
        for path, _ in sources:
            self.audit.ensure_owner(path.relative_to(self.root).as_posix(), user_id, require_registered=True)
        self.audit.ensure_owner(
            archive_path.relative_to(self.root).as_posix(), user_id, require_registered=archive_path.exists()
        )
        total = sum(path.stat().st_size for path, _ in sources)
        if total > self.max_archive_bytes:
            raise SafeFileError("Суммарный размер архива превышает лимит")
        with self._lock, self._cross_process_lock():
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=archive_path.parent, suffix=".zip", delete=False) as temporary:
                temporary_path = Path(temporary.name)
            try:
                with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for path, name in sources:
                        archive.write(path, arcname=path.relative_to(self.root).as_posix())
                if temporary_path.stat().st_size > self.max_file_bytes:
                    raise SafeFileError("Размер ZIP-файла превышает лимит")
                os.replace(temporary_path, archive_path)
                self.audit.record_file(archive_path.relative_to(self.root).as_posix(), archive_path.stat().st_size, user_id, "write")
            finally:
                temporary_path.unlink(missing_ok=True)

    def extract_zip(self, archive_name: str, destination: str, user_id: int) -> list[str]:
        with self._lock, self._cross_process_lock():
            return self._extract_zip_locked(archive_name, destination, user_id)

    def _extract_zip_locked(self, archive_name: str, destination: str, user_id: int) -> list[str]:
        archive_path = self._path(archive_name)
        destination_path = self._path(destination)
        if not archive_path.is_file():
            raise SafeFileError("ZIP-архив не найден")
        if archive_path.stat().st_size > self.max_file_bytes:
            raise SafeFileError("ZIP-файл превышает установленный лимит")
        self.audit.ensure_owner(archive_path.relative_to(self.root).as_posix(), user_id, require_registered=True)
        with self._lock, self._cross_process_lock(), zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if len(entries) > 1000:
                raise SafeFileError("В архиве слишком много записей")
            total_size = sum(entry.file_size for entry in entries)
            if total_size > self.max_archive_bytes:
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
                if entry.file_size > self.max_file_bytes:
                    raise SafeFileError("Один из файлов архива превышает лимит размера")
                ratio = entry.file_size / max(entry.compress_size, 1)
                if ratio > self.max_compression_ratio:
                    raise SafeFileError("Степень сжатия превышает допустимый предел")
            # Validate every target before any extraction and never overwrite existing data.
            targets = {}
            for entry in entries:
                output = self._path((Path(destination) / entry.filename).as_posix())
                key = os.path.normcase(str(output))
                if key in targets or output.exists():
                    raise SafeFileError("Цель ZIP уже существует или повторяется; перезапись запрещена")
                targets[key] = entry.is_dir()
            # A file named 'a' cannot also be the parent of 'a/b'. Reject the
            # entire conflicting layout before writing the first member.
            for entry in entries:
                output = self._path((Path(destination) / entry.filename).as_posix())
                for parent in output.parents:
                    if parent == self.root:
                        break
                    parent_key = os.path.normcase(str(parent))
                    if parent.is_file() or (parent_key in targets and not targets[parent_key]):
                        raise SafeFileError("Файл ZIP конфликтует с каталогом назначения")
            destination_path.mkdir(parents=True, exist_ok=True)
            extracted = []
            for entry in entries:
                if entry.is_dir():
                    self._path((Path(destination) / entry.filename).as_posix()).mkdir(parents=True, exist_ok=True)
                    continue
                output = (destination_path / Path(*PurePosixPath(entry.filename).parts)).resolve()
                if not output.is_relative_to(destination_path.resolve()):
                    raise SafeFileError("Путь из архива выходит за каталог назначения")
                relative = output.relative_to(self.root).as_posix()
                self.audit.ensure_owner(relative, user_id)
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
                self.audit.record_file(relative, output.stat().st_size, user_id, "write")
                extracted.append(relative)
            return extracted

    @staticmethod
    def list_drives() -> list[dict[str, Any]]:
        roots = []
        if hasattr(os, "listdrives"):
            roots = os.listdrives()
        elif os.name == "nt":
            roots = [f"{letter}:\\" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{letter}:\\").exists()]
        else:
            roots = ["/"]
        drives = []
        for root in roots:
            try:
                usage = shutil.disk_usage(root)
                item: dict[str, Any] = {
                    "path": root,
                    "total_bytes": usage.total,
                    "free_bytes": usage.free,
                    "available_bytes": usage.free,
                }
                if os.name == "nt":
                    drive_type = ctypes.windll.kernel32.GetDriveTypeW(root)
                    item["drive_type"] = {
                        2: "removable",
                        3: "fixed",
                        4: "network",
                        5: "optical",
                        6: "ramdisk",
                    }.get(drive_type, "unknown")
                    volume_name = ctypes.create_unicode_buffer(261)
                    file_system = ctypes.create_unicode_buffer(261)
                    ctypes.windll.kernel32.GetVolumeInformationW(
                        root, volume_name, len(volume_name), None, None, None, file_system, len(file_system)
                    )
                    item["volume_label"] = volume_name.value
                    item["file_system"] = file_system.value
                drives.append(item)
            except OSError:
                continue
        return drives
