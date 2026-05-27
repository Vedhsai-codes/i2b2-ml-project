# tests/LLM

## Running

```bash
# install test deps (one-time)
pip install pytest pytest-mock jsonschema jinja2 pydantic flask flask-restx flask-httpauth loguru pandas openai anthropic

# run the full suite
pytest tests/LLM/ -v
```

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
