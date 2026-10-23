# Команды файлового менеджера

Установка и запуск приведены в [README.md](README.md). Команды выполняются из корня репозитория. В примерах используется зарегистрированный пользователь `demo`; при запросе вводится его пароль.

## Диски и файлы

```powershell
powershell -ExecutionPolicy Bypass -File run.ps1 drives
powershell -ExecutionPolicy Bypass -File run.ps1 pwd
powershell -ExecutionPolicy Bypass -File run.ps1 write note.txt --text "Привет" --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 read note.txt --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 write note.txt --text "Новый текст" --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 list --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 delete note.txt --user demo
```

Файлы находятся в `lab1-data/files`. Каждая команда запускается отдельно.

## JSON и XML

```powershell
powershell -ExecutionPolicy Bypass -File run.ps1 json-write data.json --value '[1,2,3]' --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 json-read data.json --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 xml-write data.xml --value '<root><name>demo</name></root>' --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 xml-read data.xml --user demo
```

## ZIP

```powershell
powershell -ExecutionPolicy Bypass -File run.ps1 zip-create data.zip data.json data.xml --user demo
powershell -ExecutionPolicy Bypass -File run.ps1 zip-extract data.zip unpacked --user demo
```

Для архива и каталога распаковки используйте свободные имена. Справка по отдельной команде: `run.ps1 <команда> --help`.
