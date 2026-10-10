# LAB 1–2 — запуск

Команды выполняются в PowerShell из корня репозитория. Требуется Python 3.13+.
Для контейнеров нужен запущенный Docker Desktop с Linux engine.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -Dev
powershell -ExecutionPolicy Bypass -File scripts/run_lab1.ps1 help
powershell -ExecutionPolicy Bypass -File scripts/run_lab1.ps1 register demo
powershell -ExecutionPolicy Bypass -File scripts/run_lab1.ps1 write hello.txt --text "Привет" --user demo
powershell -ExecutionPolicy Bypass -File scripts/run_lab1.ps1 read hello.txt --user demo
```

При регистрации задайте пароль минимум из 8 символов. При операциях введите его по запросу; ввод скрыт. LAB 1 — консольное приложение, каждая команда запускается отдельно.

Проверка и демонстрация:

```powershell
.venv/Scripts/python.exe scripts/test.py
.venv/Scripts/python.exe -X utf8 scripts/demo.py
```

Локальный запуск CI/CD LAB 2:

```powershell
.venv/Scripts/python.exe scripts/validate_ci.py
powershell -ExecutionPolicy Bypass -File scripts/setup-tools.ps1
powershell -ExecutionPolicy Bypass -File scripts/ci-local.ps1
```

На GitHub workflow запускается при push и pull request.
