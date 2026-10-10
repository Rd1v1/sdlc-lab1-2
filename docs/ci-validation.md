# CI validation

**LOCAL CONFIG VALIDATED / LOCAL ACT RUN PASSED / REMOTE RUN NOT VERIFIED**

2026-09-26, Windows host, Linux Docker engine 29.0.1, act 0.2.89. Workflow main.yml выполнен целиком локально на реальном приложении; это не имитация команд echo.

Успешный run: `./scripts/ci-local.ps1 *> artifacts/act-third.log`, exit 0.

- Build: Python 3.13.7 image, venv dependencies, compileall, build image uploaded (53,601,231 bytes compressed artifact).
- Test: downloaded build image; **34 tests, OK**, JUnit uploaded (1,505 bytes compressed artifact).
- SAST: downloaded same build image; Bandit High gate passed; report uploaded (462 bytes compressed artifact).
- Deploy: multi-stage image; UID 10001 checked; loopback published port 18080 responded with application status ok; console help succeeded; runtime image uploaded (42,589,891 bytes compressed artifact); demo container removed.
- Cache: actions/cache saved dependency layers (~51 MB) locally. A final repeat checks restoration on final sources; see final progress/evidence.

`artifacts` logs and `.cache/artifacts` contain reproducible local evidence, ignored by Git. Act prints synthetic GitHub artifact URLs ending actions/runs/1; **do not use these as remote run links**. Remote API without authentication returned 404; no successful remote run is claimed.

Additional executed checks:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/validate_ci.py
.\.venv\Scripts\python.exe -m bandit -r lab1/src lab3/src -lll -f json -o artifacts/bandit-final.json
```

YAML parsed with PyYAML; stage chain and contents:read verified. Deliberate failure test produced exit 1 and JUnit failures=1. A static unsafe subprocess fixture produced a Bandit High finding and exit 1; fixture was never executed. Both assertions passed. No continue-on-error weakens gates.

Actual local failures were repaired: Unicode Windows workdir caused non-ASCII BuildKit session header; ASCII context inside container fixed it. Initial context copy omitted requirements-dev.txt; added and then all stages succeeded. These failures are not hidden as PASS.

Container shell scripts run dependencies only in container venv; local scripts only in project .venv. Docker socket access is required by local act/Docker orchestration and is documented; no hardcoded tokens.

## Final repeat

`./scripts/ci-local.ps1 *> artifacts/act-final.log`: exit 0, all four jobs successful, 34 Linux tests (2.615 s). Cache restored successfully; primary cache key hit. Final compressed artifacts: build image 53,600,233 bytes; JUnit 1,510; SAST 463; runtime image 42,588,978. Compact retained evidence: [ci-summary.txt](evidence/ci-summary.txt), [JUnit](evidence/junit.xml), [SAST](evidence/bandit.json), [source hashes](evidence/source-sha256.json).

Linux shell README commands were then executed inside the final build image: setup.sh --dev, test.sh, run_lab1.sh help, run_lab3.sh controlled example — all exit 0. `docker ps` after validation showed no running demonstration containers.
