# LAB 1 — шпаргалка защиты

Цель: консольное управление текстом, JSON/XML и ZIP с базой метаданных и аудитом.

Entry point: `lab1/src/app.py`, `run()`. `argparse` выбирает команду и проверяет аргументы; `getpass` читает пароль. `AuditStore.authenticate` сверяет scrypt через compare_digest; после входа CLI вызывает `SafeFileManager`.

Ключевые части:

1. `AuditStore`: Users/Files/Operations, foreign keys, placeholders `?`, соль 16 bytes и scrypt; пароль не сохраняется открытым.
2. `_path`: нормализует путь, ограничивает root, запрещает drive-relative/NTFS stream/device names и ссылки.
3. `write_bytes`: лимит, owner check, временный файл рядом, fsync и os.replace; finally убирает temporary.
4. `create_zip/extract_zip`: проверки путей/размера/ratio/числа entries; запрет перезаписи; проверки до распаковки.
5. `_cross_process_lock`: Windows mutex / POSIX flock и reentrancy для составных операций.

Стандартные pathlib/os нужны для путей/атомарной замены, zipfile — ZIP, json/ElementTree — форматов, sqlite3 — реляционной БД, hashlib/secrets — паролей. Сторонних runtime библиотек LAB 1 нет.

Ожидаемые ошибки перехватываются на границе CLI и дают код 2; программистские ошибки не скрываются широким except. EOF/Ctrl+C — код 130. Каждая команда завершается сама, `exit` тоже возвращает 0.

Проверка: `./scripts/test.ps1 --lab 1`. Покрыты CRUD, Unicode/spaces, отсутствующие/абсолютные пути, каталог вместо файла, permissions (инъекция PermissionError), owners, SQL-like login, malformed XML, ZIP traversal/bomb/overwrite, thread/process writes и CLI.

Demo 2–5 минут: открыть `app.py` → `SafeFileManager` → `AuditStore`; запустить `scripts/demo.py`; показать запись/изменение/чтение, JSON/XML, ZIP, list/delete, отклонение `../outside`, exit. Затем объяснить тест на гонку и таблицы БД.

SQLite разрешён страницей; stored procedures в SQLite нет. Процесс с прямым доступом к root/БД находится вне модели защиты. При аварии между записью файла и commit метаданные могут потребовать сверки; такой crash recovery не заявляется.
