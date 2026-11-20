# LAB 1–2 — запуск

Windows, PowerShell, Python 3.13+ с Expat 2.7.2+. Команды выполняются из корня репозитория.

## LAB 1

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.venv/Scripts/python.exe main.py help
.venv/Scripts/python.exe main.py register demo
.venv/Scripts/python.exe main.py write hello.txt --text "Привет" --user demo
.venv/Scripts/python.exe main.py read hello.txt --user demo
```

Для безопасного разбора XML используется `defusedxml`; `setup.ps1` устанавливает его в `.venv` из `requirements.txt`. Для указанных команд активировать `.venv` не требуется.
Проверить версию XML-парсера: `.venv/Scripts/python.exe -c "import pyexpat; print(pyexpat.EXPAT_VERSION)"`.
Если Expat старее 2.7.2, обновите базовый Python и пересоздайте `.venv`; в пределах одной ветки Python можно выполнить `<путь к новому python.exe> -m venv --upgrade .venv`, затем повторить `setup.ps1`.
Пароль задаётся при регистрации: минимум 8 символов. При файловых операциях вводите тот же пароль; ввод скрыт. Каждая команда запускается отдельно. Данные сохраняются в `lab1-data`. Для справки по команде добавьте `--help`.

## LAB 2

Ответы к защите: [SAST и DAST — объяснения и отличия](ANSWERS_LAB2.md).

Запустите Docker Desktop с Linux engine, затем выполните:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -Dev
powershell -ExecutionPolicy Bypass -File scripts/setup-tools.ps1
powershell -ExecutionPolicy Bypass -File scripts/ci-local.ps1
```

Команда запускает build → test → проверки sast и sca → deploy.
Bandit проверяет исходный код LAB 1 и блокирует deploy при проблемах High.
pip-audit проверяет установленные Python-модули окружения сборки, включая инструменты CI,
и блокирует deploy при любой известной уязвимости. Оба анализатора запускаются в Docker.
Каждый анализатор сохраняет отчёт в трёх форматах:

| Артефакт | Исходный отчёт | XML | PDF |
| --- | --- | --- | --- |
| `sast` | `bandit.json` | `bandit.xml` | `bandit.pdf` |
| `sca` | `pip-audit.json` | `pip-audit.xml` | `pip-audit.pdf` |

XML содержит сводку и полное типизированное содержимое исходного отчёта.
PDF содержит сводку, находки или список пакетов, описания уязвимостей,
исправленные версии и ошибки/пропуски. Встроенный шрифт поддерживает кириллицу.
Экспорт выполняется и при обнаружении уязвимости; исходный код завершения
анализатора сохраняется. Ошибка экспорта также блокирует deploy.

На GitHub файлы доступны в артефактах запуска. При локальном act ZIP-архивы
находятся в `.cache/artifacts/<run-id>/sast/sast.zip` и `sca/sca.zip`.
Существующий JSON можно преобразовать отдельно, без повторного сканирования:

```powershell
.venv/Scripts/python.exe scripts/security_reports.py bandit artifacts/bandit.json
.venv/Scripts/python.exe scripts/security_reports.py pip-audit artifacts/pip-audit.json
```

Файлы `.xml` и `.pdf` создаются рядом с исходным `.json`. Для экспорта и тестов
нужна подготовка `scripts/setup.ps1 -Dev`; runtime LAB 1 использует прежние зависимости.

Для повторного CI-запуска с заполненным кэшем добавьте `-Offline` к `scripts/ci-local.ps1`.
Этот ключ отключает загрузку Actions и runner-образа; для установки новых пакетов
и актуальной проверки уязвимостей pip-audit требуется доступ к PyPI.
