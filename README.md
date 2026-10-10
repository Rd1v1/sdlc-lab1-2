# LAB 1–2 — консольный файловый менеджер и CI/CD

Обе практики используют один и тот же реальный код LAB1. Проектные зависимости — только в локальной .venv; GitHub Actions собирает и тестирует этот менеджер.

## Практика 1

### Стек

Python 3.13+, стандартная библиотека: argparse/getpass для CLI, pathlib/os/shutil
для файлов, sqlite3 для базы, json и ElementTree для сериализации, zipfile для ZIP,
hashlib.scrypt и hmac для паролей. На Windows ctypes вызывает API дисков и named
mutex; на Linux fcntl предоставляет межпроцессную блокировку. Сторонних Python
пакетов для этой лабораторной нет. Общая `.venv` используется только для удобства.

### Запуск

Все команды из корня этого репозитория. Python3.13+, Docker Desktop/Linux engine там, где вызывается Docker. Проектные зависимости не устанавливаются глобально.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.venv/Scripts/python.exe scripts/test.py
.venv/Scripts/python.exe -X utf8 scripts/demo.py
powershell -ExecutionPolicy Bypass -File scripts/run_lab1.ps1 help
powershell -ExecutionPolicy Bypass -File scripts/run_lab1.ps1 register demo
powershell -ExecutionPolicy Bypass -File scripts/run_lab1.ps1 write hello.txt --text "Привет" --user demo
powershell -ExecutionPolicy Bypass -File scripts/run_lab1.ps1 read hello.txt --user demo
```



### Объяснение кода

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

### Материалы и ограничения

- [lab1-defense.md](docs/lab1-defense.md)

Исходный README лабораторной: [lab1/README.md](lab1/README.md). Он сохранён как историческая документация монорепозитория; актуальные самостоятельные команды приведены выше. Evidence относится к исходному аудиту 10.10.2026 и не выдаётся за новый запуск этого репозитория. Свежая проверка разделения — VALIDATION.md.

Уязвимые упражнения/сканеры используются только в собственном loopback-стенде. Не запускать несколько копий Docker-стенда одновременно: порты и имена сервисов фиксированы.

## Практика 2

### Стек

GitHub Actions, Docker/BuildKit, Python 3.13.7 в контейнерах, unittest с собственным
JUnit-экспортом, Bandit 1.8.6, PyYAML для проверки workflow. Локальный runner:
portable act 0.2.89 в `.tools/act`. Зависимости Python закреплены в
`requirements-dev.txt` и `requirements.txt`; они устанавливаются в `.venv`
проекта и отдельную `/app/.venv` build-контейнера. Глобальных установок нет.

LAB2 размещена в корневых Dockerfile, .github/workflows и scripts. В этой папке
находится документация; отдельного приложения вместо настоящего LAB1 здесь нет.

### Запуск

Все команды из корня этого репозитория. Python3.13+, Docker Desktop/Linux engine там, где вызывается Docker. Проектные зависимости не устанавливаются глобально.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -Dev
.venv/Scripts/python.exe scripts/test.py
.venv/Scripts/python.exe scripts/validate_ci.py
powershell -ExecutionPolicy Bypass -File scripts/setup-tools.ps1
powershell -ExecutionPolicy Bypass -File scripts/ci-local.ps1
```

Включён снимок настоящего LAB1 из исходного проекта; CI проверяет его 21 тест, а не весь монорепозиторий.

### Объяснение кода

- **build:** checkout → Buildx → local layer cache → сборка реального LAB1 и
  тестируемых модулей → docker save → артефакт build-image.
- **test:** needs build; загружает переданный образ и вызывает `scripts/test.py`.
  `JUnitResult` записывает ошибки, skips и subtest failures. JUnit извлекается
  из контейнера и сохраняется даже при провале задания.
- **sast:** needs test; Bandit анализирует код LAB1. `-lll` блокирует High;
  у Bandit нет отдельной категории Critical. JSON-отчёт сохраняется как артефакт.
- **deploy:** needs sast; собирается runtime только с LAB1, запускается UID10001,
  `/health` публикуется на 127.0.0.1:18080. Проверяются HTTP, CLI help и id -u,
  образ сохраняется, демонстрационный контейнер удаляется в always-step.

Многоступенчатый Dockerfile имеет build/test/sast/runtime. Runtime не содержит
dev-пакетов и LAB3; интерфейс управления файлами остаётся консольным. Сервис health
нужен для портовой проверки задания, а не предоставляет файловый API.
Для Cyrillic workspace act копирует build context в ASCII-путь внутри runner.
`needs` и ненулевой exit code предотвращают запуск следующих стадий при ошибке.

### Материалы и ограничения

- [lab2-defense.md](docs/lab2-defense.md)
- [ci-validation.md](docs/ci-validation.md)

Исходный README лабораторной: [lab2/README.md](lab2/README.md). Он сохранён как историческая документация монорепозитория; актуальные самостоятельные команды приведены выше. Evidence относится к исходному аудиту 10.10.2026 и не выдаётся за новый запуск этого репозитория. Свежая проверка разделения — VALIDATION.md.

Уязвимые упражнения/сканеры используются только в собственном loopback-стенде. Не запускать несколько копий Docker-стенда одновременно: порты и имена сервисов фиксированы.
