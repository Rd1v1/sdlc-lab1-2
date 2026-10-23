# Практики 1–2 — запуск и проверка

Практика 1 — консольный файловый менеджер. Практика 2 собирает, тестирует и развёртывает это же приложение.

## Подготовка

Требуются Windows, PowerShell и Python 3.13+. Откройте PowerShell в корне репозитория `sdlc-lab1-2`, где находится `run.ps1`. Для практики 1 Docker не требуется. Для практики 2 нужен работающий Docker Desktop с Linux engine.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -Dev
powershell -ExecutionPolicy Bypass -File run.ps1 help
```

Зависимости и инструменты проверки устанавливаются в `.venv`; активировать её не требуется. `run.ps1` создаёт окружение автоматически при первом запуске, но для SAST и проверки CI нужен вариант настройки `-Dev`.

## Практика 1: ручная демонстрация

Создайте пользователя и выполните команды:

```powershell
powershell -ExecutionPolicy Bypass -File run.ps1 register demo
powershell -ExecutionPolicy Bypass -File run.ps1 drives
powershell -ExecutionPolicy Bypass -File run.ps1 pwd
powershell -ExecutionPolicy Bypass -File run.ps1 write hello.txt --text "Привет" --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 read hello.txt --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 write hello.txt --text "Обновлено" --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 copy hello.txt copy.txt --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 move copy.txt moved.txt --user demo
```

При регистрации задайте пароль длиной не менее 8 символов. При каждой файловой операции вводите тот же пароль; ввод не отображается. Ожидается чтение `Привет`, а после повторной записи — `Обновлено`. Каждая команда запускается отдельно; отдельного меню или `main.py` здесь нет. При повторе используйте уже созданного пользователя, а для `copy`, `move` и ZIP — новые имена назначения.

JSON, XML и архив:

```powershell
powershell -ExecutionPolicy Bypass -File run.ps1 json-write data.json --value '[1,2,3]' --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 json-read data.json --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 xml-write data.xml --value '<root><name>demo</name></root>' --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 xml-read data.xml --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 zip-create demo.zip data.json data.xml --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 zip-extract demo.zip unpacked --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 list --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 delete moved.txt --user demo
```

Файлы находятся в `lab1-data/files`, SQLite с пользователями, метаданными и журналом — в `lab1-data/audit.sqlite3`. Все имена файлов задаются относительно рабочего каталога. Ожидаются сохранённые JSON/XML и их копии в `unpacked`; права и операции проверяются в БД автоматическими тестами.

Команды: `drives`, `register`, `list`, `read`, `write`, `delete`, `copy`, `move`, `json-write`, `json-read`, `xml-write`, `xml-read`, `zip-create`, `zip-extract`, `pwd`, `help`, `exit`. Синтаксис отдельной команды: `run.ps1 <команда> --help`.

Проверка защиты от выхода за рабочий каталог:

```powershell
powershell -ExecutionPolicy Bypass -File run.ps1 read ../outside.txt --user demo
$LASTEXITCODE
```

После правильного пароля ожидается ошибка пути и код `2`. Коды: `0` — успех, `2` — ошибка ввода/доступа/файла, `130` — прерывание. `help` показывает синтаксис, `pwd` — рабочий каталог, `exit` завершает текущий вызов.

## Проверка практики 1

Автоматические тесты и полная демонстрация на временных данных:

```powershell
.venv/Scripts/python.exe scripts/test.py
.venv/Scripts/python.exe scripts/demo.py
.venv/Scripts/python.exe -m pip check
```

Ожидаются 21 успешный тест, `DEMO PASS` и отсутствие конфликтов зависимостей. Демонстрация проверяет все основные команды и ожидаемую ошибку пути, затем удаляет только свои временные данные. Тесты сохраняют JUnit в `artifacts/junit.xml`: `tests=21`, `failures=0`, `errors=0`, `skipped=0`.

## Практика 2: локальный CI/CD

Запустите Docker Desktop и дождитесь готовности Linux engine, затем:

```powershell
docker version
.venv/Scripts/python.exe scripts/validate_ci.py
powershell -ExecutionPolicy Bypass -File scripts/setup-tools.ps1
powershell -ExecutionPolicy Bypass -File scripts/ci-local.ps1 -List
powershell -ExecutionPolicy Bypass -File scripts/ci-local.ps1
```

`docker version` должен показать и Client, и Server. Если Server недоступен, контейнерный прогон ещё не готов к запуску. `setup-tools.ps1` скачивает portable `act` в `.tools`; первый CI-прогон также загружает Actions и образы. Для повторного запуска с уже заполненным кэшем доступен `scripts/ci-local.ps1 -Offline`.

Конвейер: **build → test → sast → deploy**. Ожидаются четыре успешные стадии и итоговый код `0`. `validate_ci.py` отдельно подтверждает, что ошибочный тест и находка Bandit HIGH возвращают код `1`; сообщение `PASS` означает успешную проверку этих отрицательных сценариев.

| Стадия | Что проверить |
| --- | --- |
| build | Реальный LAB 1 собирается в Docker; сохраняется build-image и кэш слоёв |
| test | Те же 21 тест; JUnit с нулевыми failures/errors |
| sast | Bandit; число HIGH равно 0; находка HIGH блокирует deploy |
| deploy | Runtime запускается с UID 10001; `/health` возвращает `{"status":"ok"}`; работает CLI help; сохраняется образ |

Артефакты локального `act` находятся в `.cache/artifacts` (подкаталоги запусков, в том числе ZIP с `junit.xml` и `bandit.json`). Развёртывание публикует только `127.0.0.1:18080`, проверяет приложение и автоматически удаляет демонстрационный контейнер. Поэтому после успешного CI этот адрес уже не обязан отвечать. HTTP-маршрут служит проверке контейнера; файловый менеджер остаётся консольным.

На GitHub тот же workflow запускается при push и pull request. Проверяйте четыре зелёные стадии и артефакты во вкладке Actions. JUnit XML — формат отчёта; тесты написаны на Python unittest. Результаты соответствия требованиям и ограничения — в [REPORT.md](REPORT.md).

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
