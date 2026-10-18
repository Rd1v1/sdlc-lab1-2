# Практики 1–2 — файловый менеджер и CI/CD

Практика 1 — консольный файловый менеджер. Практика 2 собирает, тестирует и развёртывает это же приложение.

Запуск в PowerShell, требуется Python 3.13+:

```powershell
powershell -ExecutionPolicy Bypass -File run.ps1 help
powershell -ExecutionPolicy Bypass -File run.ps1 register demo
powershell -ExecutionPolicy Bypass -File run.ps1 write hello.txt --text "Привет" --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 read hello.txt --user demo
```

При первом запуске создаётся `.venv`. Пароль вводится скрыто, минимум 8 символов. Каждая команда запускается отдельно. Файлы и база аудита находятся в `lab1-data`.

Команды: `drives`, `register`, `list`, `read`, `write`, `delete`, `copy`, `move`, `json-write`, `json-read`, `xml-write`, `xml-read`, `zip-create`, `zip-extract`, `pwd`, `help`, `exit`. Синтаксис отдельной команды: `run.ps1 <команда> --help`.

Проверка файловых операций и демонстрация на временных данных:

```powershell
.venv/Scripts/python.exe scripts/test.py
.venv/Scripts/python.exe scripts/demo.py
```

Локальный CI/CD требует работающий Docker Desktop с Linux engine:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -Dev
.venv/Scripts/python.exe scripts/validate_ci.py
powershell -ExecutionPolicy Bypass -File scripts/setup-tools.ps1
powershell -ExecutionPolicy Bypass -File scripts/ci-local.ps1
```

Конвейер: **build → test → sast → deploy**. Ошибка блокирует следующие стадии. Сохраняются JUnit XML, SAST-отчёт и образы. На GitHub тот же workflow запускается при push и pull request. Результаты проверки и объяснение работы — в [REPORT.md](REPORT.md).

Код удобно читать с `lab1/src/app.py`:

| Модуль | Назначение |
| --- | --- |
| `app.py` | Команды, ввод пароля, сообщения и ошибки |
| `safe_file_manager.py` | Чтение, запись, удаление, JSON/XML и координация операций |
| `audit.py` | Пользователи, метаданные и журнал SQLite |
| `paths.py` | Проверка путей и границ рабочего каталога |
| `locking.py` | Блокировка между процессами |
| `archives.py` | Проверки ZIP, создание и распаковка |
| `drives.py` | Сведения о дисках |
| `errors.py` | Ошибки безопасности |
| `scripts/junit.py` | Экспорт результатов тестов для CI/CD |
