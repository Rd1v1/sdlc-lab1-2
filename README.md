# LAB 1–2 — запуск

Windows, PowerShell, Python 3.13+. Команды выполняются из корня репозитория.

## LAB 1

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
powershell -ExecutionPolicy Bypass -File run.ps1 help
powershell -ExecutionPolicy Bypass -File run.ps1 register demo
powershell -ExecutionPolicy Bypass -File run.ps1 write hello.txt --text "Привет" --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 read hello.txt --user demo
```

Зависимости устанавливаются в `.venv`. Пароль задаётся при регистрации: минимум 8 символов. При файловых операциях вводите тот же пароль; ввод скрыт. Каждая команда запускается отдельно. Данные сохраняются в `lab1-data`. Для справки по команде добавьте `--help`.

## LAB 2

Запустите Docker Desktop с Linux engine, затем выполните:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -Dev
powershell -ExecutionPolicy Bypass -File scripts/setup-tools.ps1
powershell -ExecutionPolicy Bypass -File scripts/ci-local.ps1
```

Команда запускает конвейер build → test → sast → deploy. Для LAB 1 Docker не требуется.
