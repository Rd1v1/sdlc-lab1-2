"""Запуск консольного файлового менеджера LAB 1."""
import sys

from lab1.src.app import run


if __name__ == "__main__":
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(run())
