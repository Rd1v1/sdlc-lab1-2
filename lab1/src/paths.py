"""Проверка границ каталога, имён устройств и файловых ссылок."""
from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath
from .errors import SafeFileError


def resolve_path(root: Path, name: str) -> Path:
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
    candidate = (root / name).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise SafeFileError("Путь выходит за пределы рабочего каталога") from error
    if candidate == root:
        raise SafeFileError("Ожидалось имя файла внутри рабочего каталога")
    # Local users must not be able to substitute symlinks/junctions inside the store.
    unresolved = root / name
    for part in (unresolved, *unresolved.parents):
        if part == root:
            break
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise SafeFileError("Символические ссылки и junction запрещены")
    return candidate
