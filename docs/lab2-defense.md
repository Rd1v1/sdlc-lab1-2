# LAB 2 — CI/CD и защита

[Актуальное задание](https://sdlc.yonote.ru/share/SDLC_Lab_2) прочитано 2026-09-26. Оно требует Docker + локальный runner, SAST, JUnit, cache, image artifact и local deploy. Используется GitHub Actions, поскольку origin — GitHub.

## Запуск

Из корня на Windows, Docker Desktop с Linux engine должен работать:

```powershell
./scripts/setup.ps1 -Dev
./scripts/setup-tools.ps1
./scripts/ci-local.ps1 -List
./scripts/ci-local.ps1
```

act 0.2.89 — portable `.tools/act`; официальный архив сверяется по SHA256. hashcat из того же setup нужен только LAB 3. `.cache/actions`, `.cache/act`, `.cache/artifacts` сохраняют служебные данные в проекте. На Linux положите официальный portable binary act в `.tools/act/act` и выполните `sh scripts/ci-local.sh`.

## Стадии

Workflow `.github/workflows/main.yml` запускается по push, pull_request и workflow_dispatch. GitHub stages выражены четырьмя jobs с цепочкой needs:

1. Build: checkout, Buildx, cache, контейнерная venv и закреплённые зависимости, compileall. Build image экспортируется в artifact и используется следующими jobs.
2. Test: загрузка build artifact, запуск `scripts/test.py` в контейнере. Он тестирует настоящий LAB 1 и LAB 3, пишет JUnit; ненулевой exit завершает job с ошибкой. JUnit копируется даже при failure.
3. SAST: Bandit 1.8.6 анализирует Python исходники. `-lll` означает High severity; у Bandit нет отдельного Critical. Ненулевой exit блокирует deploy. Отрицательный gate проверяется `scripts/validate_ci.py` на статическом fixture, который никогда не исполняется.
4. Deploy: multi-stage runtime image, UID 10001, health endpoint и `docker exec` console smoke; image сохраняется как artifact. Временный контейнер убирается после проверки.

`.cache/docker` хранит слои зависимостей, BuildKit дополнительно кеширует pip. Сборка выполняется из ASCII пути `/tmp/sdlc-build` внутри runner, чтобы Windows-путь проекта с кириллицей не ломал BuildKit session header.

## Артефакты и логи

В GitHub: Actions → конкретный run → jobs/logs и Artifacts. Локально act хранит artifact server данные в `.cache/artifacts`; вывод можно сохранить `./scripts/ci-local.ps1 *> artifacts/act.log`. Подтверждённые статусы находятся в `ci-validation.md`, не следует выдавать локальный run за удалённый.

Console app не имеет web UI. `/health` существует только для обязательного port mapping задания; файл через HTTP нельзя читать/изменять. Для ручного deploy:

```powershell
docker build --target runtime -t sdlc-lab1:local .
docker run -d --name sdlc-lab1-demo -p 127.0.0.1:18080:8080 sdlc-lab1:local
docker exec -it sdlc-lab1-demo python -m lab1.src.app register demo
docker exec -it sdlc-lab1-demo python -m lab1.src.app help
docker rm -f sdlc-lab1-demo
```

Данные этого демонстрационного контейнера временные. Для сохранения используется отдельный volume по явному решению пользователя.

## Безопасность и объяснение

Workflow имеет только contents:read; токенов/паролей в конфигурации нет. При необходимости private access токен передаётся через environment/локальный secret file, который игнорируется Git. Docker socket даёт runner управление Docker хоста: запускайте локально только доверенный код. Никакой системный Python environment не меняется; контейнерная venv — часть образа.

Преподавателю показать YAML, Dockerfile, JUnit с реальными testcases, SAST negative gate, успешный local run, UID 10001, ответ health и образ. Объяснить разницу между cache (ускорение повторов), artifact (передача результатов) и image (среда приложения).
