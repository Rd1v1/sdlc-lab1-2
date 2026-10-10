# syntax=docker/dockerfile:1
FROM python:3.13.7-slim AS build
WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN --mount=type=cache,target=/app/.cache/pip .venv/bin/python -m pip install --cache-dir /app/.cache/pip -r requirements.txt -r requirements-dev.txt
COPY lab1 ./lab1
COPY scripts ./scripts
COPY .github ./.github
RUN python -m compileall -q lab1/src scripts
CMD ["python", "scripts/test.py"]

FROM build AS test
RUN python scripts/test.py

FROM build AS sast
RUN mkdir -p artifacts && python -m bandit -r lab1/src -lll -f json -o artifacts/bandit.json

FROM python:3.13.7-slim AS runtime
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
WORKDIR /app
COPY --from=build --chown=app:app /app/lab1 ./lab1
RUN mkdir /app/lab1-data && chown app:app /app/lab1-data
USER 10001:10001
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=3s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"
CMD ["python", "-m", "lab1.src.health"]
