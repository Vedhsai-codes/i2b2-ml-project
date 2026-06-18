# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Shared test fixtures for the LLM module.

The prelude stubs the few i2b2 modules that require a real DB/Mozilla/pyodbc
install so ``import i2b2_cdi.LLM.llmEngine`` works on a dev laptop with only
``pip install -r short_requirements.txt`` plus the LLM-specific deps. The
stubs ship ONLY here — zero impact on production import paths (D-2.7).

``FakeCrcDataSource`` is an in-memory sqlite-backed context manager that
translates Postgres-style placeholders (``%(name)s`` and ``%s``) into the
sqlite forms (``:name`` and ``?``). Order matters: named first so the
unnamed-``%s`` pass doesn't accidentally match ``s`` inside ``%(name)s``
(D-2.6).
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import sys
import types
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# live_pg marker — deselect when prerequisites aren't met
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    """True iff `docker` is on PATH. Does NOT probe the daemon.

    Daemon liveness is checked inside the live_pg fixtures; if docker is
    installed but Docker Desktop isn't running, the operator sees a clear
    fixture-level error rather than the test being silently skipped.
    """
    return shutil.which("docker") is not None


def pytest_collection_modifyitems(config, items):
    """Deselect (not just skip) ``live_pg`` items when RUN_LIVE_PG isn't set
    or Docker isn't installed.

    Deselection (rather than skip) satisfies two contracts:
      - ``pytest tests/LLM/`` reports the deselected count so nothing is
        silently dropped from view.
      - ``pytest tests/LLM/ -m live_pg`` reports "0 collected" because the
        items are removed from the list before pytest's marker filter runs.

    Set ``RUN_LIVE_PG=1`` and ensure ``docker`` is on PATH to opt in.
    """
    if os.environ.get("RUN_LIVE_PG") == "1" and _docker_available():
        return

    if os.environ.get("RUN_LIVE_PG") != "1":
        reason = "RUN_LIVE_PG=1 not set"
    else:
        reason = "docker not on PATH"

    deselected = []
    remaining = []
    for item in items:
        if "live_pg" in item.keywords:
            deselected.append(item)
        else:
            remaining.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = remaining
        # Stash the reason so tests/fixtures can read it for diagnostics.
        config._live_pg_skip_reason = reason


# ---------------------------------------------------------------------------
# Prelude — stub external/native modules BEFORE i2b2_cdi.LLM is imported.
# ---------------------------------------------------------------------------

os.environ.setdefault("CRC_DB_TYPE", "pg")
os.environ.setdefault("CRC_DB_NAME", "i2b2demodata")
os.environ.setdefault("ONT_DB_NAME", "i2b2metadata")
os.environ.setdefault("ENABLE_PATIENT_FACT", "True")


# Make the project root importable when pytest is invoked from anywhere.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# Stub psycopg2 (heavy native dep) BEFORE the real i2b2_cdi.database tries to import it.
# When RUN_LIVE_PG=1 is set, skip the stubs and let the real packages load so the
# live_pg tests can open actual Postgres connections.
_RUN_LIVE_PG = os.environ.get("RUN_LIVE_PG") == "1"

if not _RUN_LIVE_PG and "psycopg2" not in sys.modules:
    _psy = types.ModuleType("psycopg2")
    _psy.Error = type("Error", (Exception,), {})
    sys.modules["psycopg2"] = _psy
if not _RUN_LIVE_PG and "pyodbc" not in sys.modules:
    _odb = types.ModuleType("pyodbc")
    _odb.Error = type("Error", (Exception,), {})
    sys.modules["pyodbc"] = _odb
if "tabulate" not in sys.modules:
    _tab = types.ModuleType("tabulate")
    _tab.tabulate = lambda *a, **kw: ""
    sys.modules["tabulate"] = _tab


# Import the REAL i2b2_cdi package first so subsequent child-stub injection
# attaches to the real package object instead of replacing it with a bare
# ModuleType. The real i2b2_cdi/__init__.py is empty (license header only),
# so this is safe.
import i2b2_cdi  # noqa: E402


def _ensure_module(name: str, **attrs) -> types.ModuleType:
    """Install a stub module under ``name`` without trampling a real parent.

    If ``name`` is already in sys.modules (e.g. real package), augments it
    with the given attrs. Otherwise creates a fresh ModuleType and attaches
    it both to sys.modules and as an attribute on its parent (creating
    parents only when they are not already present, again to avoid trampling).
    """
    if name in sys.modules:
        mod = sys.modules[name]
    else:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    for k, v in attrs.items():
        setattr(mod, k, v)
    parent_name, _, child = name.rpartition(".")
    if parent_name:
        parent = _ensure_module(parent_name)
        setattr(parent, child, mod)
    return mod


# Mozilla / cdi_database_connections stubs
_ensure_module("Mozilla")
_ensure_module("Mozilla.exception")
_ensure_module(
    "Mozilla.exception.mozilla_cdi_database_error",
    MozillaCdiDatabaseError=type("MozillaCdiDatabaseError", (Exception,), {}),
)


class _StubDataSource:
    """Construction is a no-op (lazy production imports must not blow up).

    Any test that actually opens a cursor without monkey-patching this with a
    real fixture trips the AssertionError in __enter__ — loud failure beats
    silent half-success (D-4.7).
    """

    def __init__(self, *args, **kwargs):
        self.database = kwargs.get("database") or "i2b2demodata"
        self.dbType = os.environ.get("CRC_DB_TYPE", "pg")
        self.ip = "localhost"
        self.port = 5432
        self.username = "i2b2"
        self.password = "demouser"

    def __enter__(self):
        raise AssertionError(
            "_StubDataSource.__enter__ called without a DB fixture monkey-patching it"
        )

    def __exit__(self, exc_type, exc, tb):
        return False


_ensure_module(
    "i2b2_cdi.database.cdi_database_connections",
    I2b2crcDataSource=_StubDataSource,
    I2b2metaDataSource=_StubDataSource,
    I2b2pmDataSource=_StubDataSource,
)


class _StubConfig:
    """Config().new_config(argv=[...]) → a self-returning object."""

    crc_db_type = os.environ.get("CRC_DB_TYPE", "pg")

    def new_config(self, *args, **kwargs):
        return self

    def __getattr__(self, item):
        return ""


_ensure_module("i2b2_cdi.config", config=_ensure_module("i2b2_cdi.config.config"))
sys.modules["i2b2_cdi.config.config"].Config = _StubConfig


# Stub the heavy fact/concept runners used by BaseEngine.send_facts /
# LLM concept_API — they pull psycopg2 transitively. Replace mod_run with
# a no-op that records the call.
def _noop_mod_run(*args, **kwargs):
    return types.SimpleNamespace(empty=True)


_ensure_module("i2b2_cdi.fact", runner=_ensure_module("i2b2_cdi.fact.runner"))
sys.modules["i2b2_cdi.fact.runner"].mod_run = _noop_mod_run
_ensure_module("i2b2_cdi.concept", runner=_ensure_module("i2b2_cdi.concept.runner"))
sys.modules["i2b2_cdi.concept.runner"].mod_run = _noop_mod_run


# ---------------------------------------------------------------------------
# Sqlite-backed FakeCrcDataSource
# ---------------------------------------------------------------------------


_NAMED_PLACEHOLDER_RE = re.compile(r"%\(([A-Za-z_][A-Za-z0-9_]*)\)s")


def _build_schema_prefix_re():
    """Strip ``$CRC_DB_NAME.`` prefixes (the H-5 schema-qualified form).

    Sqlite has no schema concept (``i2b2demodata.observation_fact`` would be
    interpreted as an attached database). Production code now qualifies all
    table references with the CRC schema name, so the test translator must
    strip that prefix before forwarding to sqlite.
    """
    schema = os.environ.get("CRC_DB_NAME", "i2b2demodata")
    # Escape regex meta-characters in case CRC_DB_NAME ever contains them.
    return re.compile(r"\b" + re.escape(schema) + r"\.")


_SCHEMA_PREFIX_RE = _build_schema_prefix_re()


class _TranslatingCursor:
    """Wraps a sqlite cursor; translates PG-style placeholders to sqlite forms."""

    def __init__(self, real_cursor):
        self._real = real_cursor

    @staticmethod
    def _translate(sql: str) -> str:
        # Strip CRC schema prefix (H-5): "i2b2demodata.observation_fact" → "observation_fact"
        sql = _SCHEMA_PREFIX_RE.sub("", sql)
        sql = _NAMED_PLACEHOLDER_RE.sub(r":\1", sql)
        sql = sql.replace("%s", "?")
        sql = sql.replace("ilike", "LIKE").replace("ILIKE", "LIKE")
        return sql

    def execute(self, sql, params=None):
        sql = self._translate(sql)
        if params is None:
            return self._real.execute(sql)
        if isinstance(params, dict):
            return self._real.execute(sql, params)
        return self._real.execute(sql, tuple(params))

    def executemany(self, sql, seq_of_params):
        sql = self._translate(sql)
        return self._real.executemany(sql, seq_of_params)

    def fetchone(self):
        return self._real.fetchone()

    def fetchall(self):
        return self._real.fetchall()

    @property
    def rowcount(self):
        return self._real.rowcount

    @property
    def description(self):
        return self._real.description

    def close(self):
        self._real.close()


class FakeCrcDataSource:
    """Sqlite-backed CRC data source. Context manager yields a translating cursor."""

    def __init__(self, conn: sqlite3.Connection):
        self.connection = conn
        self.database = "i2b2demodata"
        self.dbType = "pg"
        self._cursor: Any = None

    def __enter__(self):
        self._cursor = _TranslatingCursor(self.connection.cursor())
        return self._cursor

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.connection.commit()
        if self._cursor is not None:
            self._cursor.close()
        return False


def _build_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS job (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT,
            priority INTEGER,
            input TEXT,
            status TEXT,
            job_type TEXT,
            started_on TEXT,
            completed_on TEXT,
            output TEXT,
            error_stack TEXT,
            job_host TEXT
        );
        CREATE TABLE IF NOT EXISTS concept_dimension (
            concept_cd TEXT PRIMARY KEY,
            concept_path TEXT,
            name_char TEXT,
            concept_blob TEXT,
            definition_type TEXT
        );
        CREATE TABLE IF NOT EXISTS observation_fact (
            patient_num INTEGER,
            concept_cd TEXT,
            start_date TEXT,
            nval_num REAL,
            observation_blob TEXT
        );
        CREATE TABLE IF NOT EXISTS llm_audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            patient_num INTEGER,
            concept_cd TEXT,
            provider_name TEXT NOT NULL,
            model_name TEXT NOT NULL,
            prompt_hash TEXT NOT NULL,
            prompt_text TEXT,
            response_text TEXT,
            parsed_output TEXT,
            finish_reason TEXT,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            cost_usd REAL,
            latency_ms INTEGER,
            guardrail_outcome TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()


@pytest.fixture
def sqlite_conn():
    conn = sqlite3.connect(":memory:")
    _build_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def fake_crc(sqlite_conn):
    return FakeCrcDataSource(sqlite_conn)


@pytest.fixture
def patch_crc_ds(monkeypatch, fake_crc):
    """Point every production import site at our sqlite-backed fake."""
    import i2b2_cdi.LLM.audit as audit_mod
    import i2b2_cdi.LLM.apply_LLM as apply_mod
    import i2b2_cdi.LLM.perform_LLM as perform_mod

    monkeypatch.setattr(
        "i2b2_cdi.database.cdi_database_connections.I2b2crcDataSource",
        lambda *a, **kw: fake_crc,
        raising=True,
    )
    monkeypatch.setattr(
        "i2b2_cdi.job.BaseEngine.I2b2crcDataSource",
        lambda *a, **kw: fake_crc,
        raising=False,
    )
    return fake_crc


@pytest.fixture
def seed_concept(sqlite_conn):
    def _do(code: str, path: str, blob: dict):
        import json as _json

        sqlite_conn.execute(
            "INSERT INTO concept_dimension (concept_cd, concept_path, name_char, concept_blob, definition_type) "
            "VALUES (?, ?, ?, ?, ?)",
            (code, path, code, _json.dumps(blob), "LLM-BUILD"),
        )
        sqlite_conn.commit()
    return _do


@pytest.fixture
def seed_patient_notes(sqlite_conn):
    def _do(patient_num: int, note_path: str, note_text: str, code: str = "NOTE:DISCHARGE"):
        sqlite_conn.execute(
            "INSERT OR IGNORE INTO concept_dimension "
            "(concept_cd, concept_path, name_char, concept_blob, definition_type) "
            "VALUES (?, ?, ?, ?, ?)",
            (code, note_path, code, "{}", "NOTE"),
        )
        sqlite_conn.execute(
            "INSERT INTO observation_fact (patient_num, concept_cd, start_date, observation_blob) "
            "VALUES (?, ?, ?, ?)",
            (patient_num, code, "2018-01-01", note_text),
        )
        sqlite_conn.commit()
    return _do
