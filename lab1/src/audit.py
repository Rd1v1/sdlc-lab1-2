"""Пользователи, права на файлы, метаданные и журнал SQLite."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
from pathlib import Path
from typing import Any
from .errors import SafeFileError


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
