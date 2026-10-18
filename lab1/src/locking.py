"""Повторно входимая межпроцессная блокировка файлового хранилища."""
from __future__ import annotations

import contextlib
import ctypes
import hashlib
import os
from pathlib import Path


@contextlib.contextmanager
def file_lock(root: Path, state):
    depth = getattr(state, "depth", 0)
    if depth:
        state.depth = depth + 1
        try:
            yield
        finally:
            state.depth -= 1
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
        key = hashlib.sha256(os.path.normcase(str(root)).encode("utf-8")).hexdigest()
        mutex = kernel.CreateMutexW(None, False, f"Local\\Lab1FileManager_{key}")
        if not mutex:
            raise OSError("Не удалось создать межпроцессную блокировку")
        wait_result = kernel.WaitForSingleObject(mutex, 0xFFFFFFFF)
        if wait_result not in (0, 0x80):
            kernel.CloseHandle(mutex)
            raise OSError("Не удалось получить межпроцессную блокировку")
        state.depth = 1
        try:
            yield
        finally:
            state.depth = 0
            kernel.ReleaseMutex(mutex)
            kernel.CloseHandle(mutex)
        return

    import fcntl

    lock_path = root.parent / f".{root.name}.lock"
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        state.depth = 1
        try:
            yield
        finally:
            state.depth = 0
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
