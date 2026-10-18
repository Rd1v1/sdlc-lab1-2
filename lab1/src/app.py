from __future__ import annotations

import argparse
import getpass
import json
import sqlite3
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from .audit import AuditStore
from .errors import SafeFileError
from .safe_file_manager import SafeFileManager


DATA_ROOT = Path("lab1-data/files")
AUDIT_DATABASE = Path("lab1-data/audit.sqlite3")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Локальный безопасный файловый менеджер",
                                     epilog="Также: help — справка и рабочий каталог; pwd — каталог; exit — выход. write заменяет содержимое своего файла.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("drives", help="Показать сведения о локальных дисках")
    register = commands.add_parser("register", help="Создать локального пользователя")
    register.add_argument("username")
    listing = commands.add_parser("list", help="Список файлов рабочего каталога")
    listing.add_argument("--user", required=True)

    for name in ("read", "delete", "json-read", "xml-read"):
        command = commands.add_parser(name)
        command.add_argument("name")
        command.add_argument("--user", required=True)

    write = commands.add_parser("write", help="Записать UTF-8 текст")
    write.add_argument("name")
    write.add_argument("--text", required=True)
    write.add_argument("--user", required=True)

    for name in ("copy", "move"):
        command = commands.add_parser(name, help="Безопасное копирование или перемещение")
        command.add_argument("source")
        command.add_argument("destination")
        command.add_argument("--user", required=True)
    json_write = commands.add_parser("json-write", help="Записать JSON")
    json_write.add_argument("name")
    json_write.add_argument("--value", required=True)
    json_write.add_argument("--user", required=True)
    xml_write = commands.add_parser("xml-write", help="Записать XML")
    xml_write.add_argument("name")
    xml_write.add_argument("--value", required=True)
    xml_write.add_argument("--user", required=True)
    archive = commands.add_parser("zip-create", help="Создать ZIP из файлов рабочего каталога")
    archive.add_argument("archive")
    archive.add_argument("files", nargs="+")
    archive.add_argument("--user", required=True)
    extract = commands.add_parser("zip-extract", help="Безопасно извлечь ZIP")
    extract.add_argument("archive")
    extract.add_argument("destination")
    extract.add_argument("--user", required=True)
    return parser


def run(arguments: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if not arguments or arguments == ["help"]:
        build_parser().print_help()
        print(f"Рабочий каталог: {DATA_ROOT.resolve()}")
        return 0
    if arguments == ["exit"]:
        return 0
    if arguments == ["pwd"]:
        print(DATA_ROOT.resolve())
        return 0
    options = build_parser().parse_args(arguments)
    if options.command == "drives":
        print(json.dumps(SafeFileManager.list_drives(), ensure_ascii=False, indent=2))
        return 0
    try:
        store = AuditStore(AUDIT_DATABASE)
        try:
            if options.command == "register":
                store.create_user(options.username, getpass.getpass("Пароль (не менее 8 символов): "))
                print("Пользователь создан")
                return 0
            password = getpass.getpass("Пароль: ")
            user_id = store.authenticate(options.user, password)
            if user_id is None:
                raise SafeFileError("Неверный логин или пароль")
            manager = SafeFileManager(DATA_ROOT, store)
            if options.command == "list":
                store.record_activity("list", "", user_id)
                print(json.dumps(manager.list_files(user_id), ensure_ascii=False, indent=2))
            elif options.command == "write":
                manager.write_text(options.name, options.text, user_id)
                print("Файл сохранён")
            elif options.command == "read":
                print(manager.read_text(options.name, user_id))
            elif options.command == "delete":
                manager.delete(options.name, user_id)
                print("Файл удалён")
            elif options.command == "copy":
                manager.copy_file(options.source, options.destination, user_id)
                print("Файл скопирован")
            elif options.command == "move":
                manager.move_file(options.source, options.destination, user_id)
                print("Файл перемещён")
            elif options.command == "json-write":
                manager.write_json(options.name, json.loads(options.value), user_id)
                print("JSON сохранён")
            elif options.command == "json-read":
                print(json.dumps(manager.read_json(options.name, user_id), ensure_ascii=False, indent=2))
            elif options.command == "xml-write":
                manager.write_xml(options.name, options.value, user_id)
                print("XML сохранён")
            elif options.command == "xml-read":
                print(ET.tostring(manager.read_xml(options.name, user_id), encoding="unicode"))
            elif options.command == "zip-create":
                manager.create_zip(options.archive, options.files, user_id)
                print("ZIP создан")
            elif options.command == "zip-extract":
                print(json.dumps(manager.extract_zip(options.archive, options.destination, user_id), ensure_ascii=False))
            return 0
        finally:
            store.close()
    except (EOFError, KeyboardInterrupt):
        print("Ввод прерван", file=sys.stderr)
        return 130
    except (SafeFileError, OSError, sqlite3.Error, json.JSONDecodeError, UnicodeError, zipfile.BadZipFile) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
