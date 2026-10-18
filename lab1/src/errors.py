"""Ошибки безопасности и проверки пользовательского ввода."""
from __future__ import annotations




class SafeFileError(ValueError):
    """Raised when an operation violates a file-manager security limit."""
