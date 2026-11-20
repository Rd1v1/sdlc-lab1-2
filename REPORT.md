# Команды файлового менеджера

Установка и запуск приведены в [README.md](README.md). Команды выполняются из корня репозитория. В примерах используется зарегистрированный пользователь `demo`; при запросе вводится его пароль.

## Диски и файлы

```powershell
.venv/Scripts/python.exe main.py drives
.venv/Scripts/python.exe main.py pwd
.venv/Scripts/python.exe main.py write note.txt --text "Привет" --user demo
.venv/Scripts/python.exe main.py read note.txt --user demo
.venv/Scripts/python.exe main.py write note.txt --text "Новый текст" --user demo
.venv/Scripts/python.exe main.py list --user demo
.venv/Scripts/python.exe main.py delete note.txt --user demo
```

Файлы находятся в `lab1-data/files`. Каждая команда запускается отдельно.

## JSON и XML

```powershell
.venv/Scripts/python.exe main.py json-write data.json --value '[1,2,3]' --user demo
.venv/Scripts/python.exe main.py json-read data.json --user demo
.venv/Scripts/python.exe main.py xml-write data.xml --value '<root><name>demo</name></root>' --user demo
.venv/Scripts/python.exe main.py xml-read data.xml --user demo
```

XML разбирается через `defusedxml` с `forbid_dtd=True`, `forbid_entities=True`
и `forbid_external=True`: DTD, пользовательские сущности и внешние ссылки запрещены.
Стандартные `&amp;`, `&lt;`, `&gt;`, `&quot;`, `&apos;`, числовые ссылки,
пространства имён, комментарии и CDATA поддерживаются. Текст `<!DOCTYPE ...>`
внутри комментария или CDATA не считается объявлением DTD.

До разбора проверяется размер XML в байтах UTF-8: по умолчанию не более 1 МиБ.
При чтении также проверяется размер файла на диске. Ошибки синтаксиса и защиты
преобразуются в `SafeFileError`. XML-операции требуют Expat 2.7.2+; `setup.ps1`
проверяет эту версию. Отдельного ограничения глубины XML в приложении нет.
Зависимость закреплена в `requirements.txt` и установлена также в runtime Docker.

## ZIP

```powershell
.venv/Scripts/python.exe main.py zip-create data.zip data.json data.xml --user demo
.venv/Scripts/python.exe main.py zip-extract data.zip unpacked --user demo
```

Для архива и каталога распаковки используйте свободные имена. Справка по отдельной команде: `.venv/Scripts/python.exe main.py <команда> --help`.

## Журнал и откат операций

Неуспешные команды аутентифицированного пользователя записываются в `Operations`
с типом `read_failed`, `write_failed`, `delete_failed` и аналогичными типами
для JSON/XML/ZIP. В `detail` хранится JSON с путём и причиной; для ZIP также
сохраняются имена исходных файлов или каталог назначения. Пароли, записываемый
текст и содержимое JSON/XML в журнал ошибок не включаются.

При обрабатываемой ошибке файловой операции или фиксации SQLite восстанавливаются
предыдущее содержимое, режим доступа и время изменения затронутых файлов.
Новые файлы и созданные операцией пустые каталоги удаляются. Это относится
к записи, удалению, созданию и извлечению ZIP, включая частично выполненное
извлечение. Вложенная ошибка отменяет всю внешнюю транзакцию.

Снимки файлов хранятся в памяти до фиксации транзакции; восстановление выполняется
до освобождения блокировки SQLite. Это компенсация обработанных ошибок,
а не восстановление после аварийного завершения процесса или отключения питания.
