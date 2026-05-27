# tests/LLM

## Running

```bash
# install test deps (one-time)
pip install pytest pytest-mock jsonschema jinja2 pydantic flask flask-restx \
            flask-httpauth loguru pandas openai anthropic tabulate

# run the full suite
pytest tests/LLM/ -v
```

### Note on `tabulate`

`conftest.py` installs a stub for `tabulate` so that `pytest` itself never
needs the real package. However, two adjacent workflows DO need it:

1. **Running module code outside pytest** — e.g., `python -c "from
   i2b2_cdi.LLM.providers.local_hf import LocalHFProvider"` from a path
   that also triggers the loader's transitive imports. The stub doesn't
   help here because the runtime walks `sys.modules` and trips on the
   bare `ModuleType`.
2. **Booting the Flask app** — `i2b2_cdi/loader/app_helper.py` imports
   `from tabulate import tabulate` for diagnostic output.

The minimal install line above includes `tabulate` so a developer who never
runs `pip install -r requirements.txt` still gets it. Production deploys
that use `requirements.txt` already have it (line 156, `tabulate==0.9.0`).

Tests use an in-memory sqlite via `FakeCrcDataSource` (see `conftest.py`) and
stub modules that require psycopg2/Mozilla. No real network calls.

## Live-PG smoke test

The acceptance-level smoke (`pytest -m live_pg`) is documented but not
automated here — it requires a running Postgres + the `llm_audit` migration
applied + a real `jobWatcher` daemon. Procedure:

```bash
docker-compose up -d
docker exec -it i2b2-etl bash -c \
    "source /usr/src/app/.venv/bin/activate && \
     python -m i2b2_cdi.job.jobWatcher &"
# Then POST a job and watch llm_audit + observation_fact populate.
```

## Adding a test

- Use the `fake_crc` + `sqlite_conn` fixtures for DB-touching tests.
- Use `MockProvider` (from `tests/LLM/fixtures/mock_provider.py`) for any
  provider call. The `register_mock` fixture pattern in `test_providers.py`
  shows how to register/unregister cleanly.
- Never make real network or LLM calls in CI.
