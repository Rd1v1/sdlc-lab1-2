# LAB 1 — Безопасный файловый менеджер

## Цель и архитектура

Консольное приложение разделяет CLI (`src/app.py`), файловую логику (`src/safe_file_manager.py`) и SQLite-аудит (`AuditStore`). Приложение ограничивает root, проверяет владельца файлов, использует атомарную замену при записи и безопасно извлекает ZIP.

## Стек и зависимости

Python 3.13+, стандартная библиотека: argparse/getpass для CLI, pathlib/os/shutil
для файлов, sqlite3 для базы, json и ElementTree для сериализации, zipfile для ZIP,
hashlib.scrypt и hmac для паролей. На Windows ctypes вызывает API дисков и named
mutex; на Linux fcntl предоставляет межпроцессную блокировку. Сторонних Python
пакетов для этой лабораторной нет. Общая `.venv` используется только для удобства.

## Как устроен код

1. `app.build_parser()` описывает команды; `app.run()` обрабатывает help/pwd/exit,
   регистрирует пользователя либо спрашивает пароль и вызывает файловый метод.
2. `AuditStore` создаёт Users, Files, Operations. Пароль превращается в scrypt
   с 16-байтовой случайной солью; проверка использует compare_digest. SQL-параметры
   передаются отдельно от текста запроса, операции БД выполняются в транзакциях.
3. `SafeFileManager._path()` разрешает относительные имена внутри root: запрещены
   выход за root, дисковые пути, NTFS streams, device names и ссылки.
   `ensure_owner()` сверяет владельца с Files до доступа к содержимому.
4. Запись сохраняет временный файл, flush/fsync, затем os.replace; после этого
   обновляет размер и аудит. RLock и mutex/flock сериализуют процессы приложения.
   Move использует hard link + unlink, чтобы не заменять существующую цель.
5. JSON проходит json.loads/dumps, XML отвергает DTD/entity перед ElementTree.
   ZIP заранее проверяет имена, размеры, степень сжатия, ссылки, дубликаты
   и конфликты файла с каталогом. Пустые каталоги при извлечении сохраняются.

ОС-файл и SQLite не объединены в одну транзакцию: авария между файловой записью
и фиксацией метаданных требует восстановления вручную. Защита рассчитана на
пользователей приложения; администратор ОС может изменять файлы в обход него.

## Автоматическая демонстрация и тесты

Команды выполняются из корня репозитория:

```powershell
.venv/Scripts/python.exe -X utf8 scripts/demo.py
.venv/Scripts/python.exe scripts/test.py --lab 1
```

Demo создаёт временное хранилище в `.tmp`, проводит CRUD/copy/move/JSON/XML/ZIP,
проверяет ожидаемые ошибки и удаляет только свои временные данные. Настоящий
getpass в автоматизации заменён учебным значением. Для ручной защиты используйте
команды ниже. `scripts/test.py` создаёт JUnit в artifacts/junit.xml и возвращает 1
при провале теста; ошибка пользовательской CLI-команды имеет код 2.

## Запуск

Из корня проекта (Python 3.13; venv необязателен для LAB 1):

```powershell
py -3.13 lab1\src\app.py drives
py -3.13 lab1\src\app.py register demo
py -3.13 lab1\src\app.py write notes\hello.txt --text "Привет" --user demo
py -3.13 lab1\src\app.py read notes\hello.txt --user demo
py -3.13 lab1\src\app.py list --user demo
```

Для операций с файлами пароль запрашивается через скрытый prompt; help/pwd/exit/drives не требуют входа. Пути задаются приложением: root `lab1-data/files`, база `lab1-data/audit.sqlite3` относительно рабочего каталога запуска. CLI не предоставляет пользователю параметров переноса sandbox.

## Команды

- `drives` — сведения о логических дисках.
- `register USER` — регистрация; пароль длиной 8-1024 символа, хранится как scrypt hash с отдельной солью.
- `list --user USER`, `read NAME --user USER`, `write NAME --text TEXT --user USER`, `delete NAME --user USER`.
- `copy SOURCE DEST --user USER`, `move SOURCE DEST --user USER`; существующая цель не перезаписывается.
- `json-write NAME --value JSON --user USER`, `json-read NAME --user USER`.
- `xml-write NAME --value XML --user USER`, `xml-read NAME --user USER`; DTD/entity запрещены.
- `zip-create ARCHIVE FILE... --user USER`, `zip-extract ARCHIVE DEST --user USER`.

Лимиты по умолчанию: 1 MiB на файл, 10 MiB распакованных данных и коэффициент сжатия 100:1. Извлечение также запрещает абсолютные/traversal пути, symlink entries и более 1000 элементов.

## Проверки и примеры

```powershell
py -3.13 -m unittest discover -s lab1\tests -v
```

Входные данные находятся в `examples/`. Неуспешный вход/файловые операции печатают сообщение `Ошибка: ...` и завершаются с кодом 2.

## Ограничения

Все переменные SQL передаются через placeholders. SQLite не предоставляет stored procedures; приложение использует parameterized statements и транзакционные методы репозитория, но это не эквивалент нативной хранимой процедуре. Это ограничение рекомендованной архитектуры отмечено в матрице; SQLite явно разрешён функциональными требованиями. Актуальная шпаргалка: docs/lab1-defense.md.
