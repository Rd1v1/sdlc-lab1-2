# LAB 2 — CI/CD файлового менеджера

## Стек

GitHub Actions, Docker/BuildKit, Python 3.13.7 в контейнерах, unittest с собственным
JUnit-экспортом, Bandit 1.8.6, PyYAML для проверки workflow. Локальный runner:
portable act 0.2.89 в `.tools/act`. Зависимости Python закреплены в
`requirements-dev.txt` и `lab3/requirements.txt`; они устанавливаются в `.venv`
проекта и отдельную `/app/.venv` build-контейнера. Глобальных установок нет.

LAB2 размещена в корневых Dockerfile, .github/workflows и scripts. В этой папке
находится документация; отдельного приложения вместо настоящего LAB1 здесь нет.

## Инструкция

Требуются Python 3.13+, Git и уже установленный Docker Desktop с Linux engine.
Все команды — из корня проекта, PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -Dev
powershell -ExecutionPolicy Bypass -File scripts/setup-tools.ps1
powershell -ExecutionPolicy Bypass -File scripts/ci-local.ps1 -List
powershell -ExecutionPolicy Bypass -File scripts/ci-local.ps1
```

Setup скачивает инструменты в `.tools`, пакеты — в `.venv`, кэш — в `.cache`.
`-List` показывает задания без выполнения. Полный запуск требует сети для
официальных Actions/образов; логи следует сохранять в artifacts, например
`scripts/ci-local.ps1 > artifacts/ci-local.log 2>&1`.

```powershell
.venv/Scripts/python.exe scripts/test.py
.venv/Scripts/python.exe scripts/validate_ci.py
```

Первая команда запускает общий набор LAB1/3/4/5 и пишет artifacts/junit.xml.
Вторая реально проверяет отказ unit-test gate и SAST High gate на временных
учебных фикстурах. Статическая опасная фикстура не исполняется.

## Как устроен код

- **build:** checkout → Buildx → local layer cache → сборка реального LAB1 и
  тестируемых модулей → docker save → артефакт build-image.
- **test:** needs build; загружает переданный образ и вызывает `scripts/test.py`.
  `JUnitResult` записывает ошибки, skips и subtest failures. JUnit извлекается
  из контейнера и сохраняется даже при провале задания.
- **sast:** needs test; Bandit анализирует код LAB1/3/4/5. `-lll` блокирует High;
  у Bandit нет отдельной категории Critical. JSON-отчёт сохраняется как артефакт.
- **deploy:** needs sast; собирается runtime только с LAB1, запускается UID10001,
  `/health` публикуется на 127.0.0.1:18080. Проверяются HTTP, CLI help и id -u,
  образ сохраняется, демонстрационный контейнер удаляется в always-step.

Многоступенчатый Dockerfile имеет build/test/sast/runtime. Runtime не содержит
dev-пакетов и LAB3; интерфейс управления файлами остаётся консольным. Сервис health
нужен для портовой проверки задания, а не предоставляет файловый API.
Для Cyrillic workspace act копирует build context в ASCII-путь внутри runner.
`needs` и ненулевой exit code предотвращают запуск следующих стадий при ошибке.

## Артефакты и ограничения

Если Actions и runner image уже скачаны, при проблеме DNS можно повторить с
`powershell -ExecutionPolicy Bypass -File scripts/ci-local.ps1 -Offline`.
Этот флаг запрещает повторную загрузку Actions/runner image. Docker build всё
ещё может потребовать сеть для отсутствующей base image или зависимости.
Offline run — настоящее выполнение workflow с локальным кэшем, а не пропуск стадий.

Локальные Actions-артефакты лежат в `.cache/artifacts`; новые логи аудита —
`artifacts/audit-2026-10-10`. Итог проверки: [аудит](../docs/audit-2026-10-10.md).
Локальный act и удалённый GitHub run — разные доказательства. Удалённый запуск
без доступа/публикации не заявляется проверенным. Build runner получает Docker
socket для сборки; application runtime этот доступ не получает.
Кэш ускоряет повторную сборку, но не считается подтверждением прохождения тестов.
