# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Tests for ``audit.PromptAuditLogger``."""
from __future__ import annotations

import json

import pytest

from i2b2_cdi.LLM.audit import PromptAuditLogger


def _kwargs(**over):
    base = dict(
        job_id=1,
        patient_num=42,
        concept_cd="HF_LLM",
        provider_name="mock",
        model_name="mock-1",
        prompt_hash="0" * 64,
        prompt_text="please label",
        response_text='<json>{"label":1}</json>',
        parsed_output={"label": 1, "confidence": 0.9},
        finish_reason="stop",
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.0,
        latency_ms=12,
        guardrail_outcome="passed",
    )
    base.update(over)
    return base


def _rows(sqlite_conn):
    cur = sqlite_conn.cursor()
    cur.execute("SELECT * FROM llm_audit ORDER BY audit_id")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def test_audit_log_writes_one_row_full_mode(fake_crc, sqlite_conn):
    log = PromptAuditLogger(fake_crc, audit_level="full")
    ok = log.log(**_kwargs())
    assert ok is True
    rows = _rows(sqlite_conn)
    assert len(rows) == 1
    r = rows[0]
    assert r["prompt_text"] == "please label"
    assert r["response_text"] == '<json>{"label":1}</json>'
    assert json.loads(r["parsed_output"]) == {"label": 1, "confidence": 0.9}
    assert log.audit_rows_written == 1


def test_audit_log_redacts_text_in_redacted_mode(fake_crc, sqlite_conn):
    log = PromptAuditLogger(fake_crc, audit_level="redacted")
    log.log(**_kwargs())
    rows = _rows(sqlite_conn)
    assert rows[0]["prompt_text"] is None
    assert rows[0]["response_text"] is None
    assert json.loads(rows[0]["parsed_output"]) == {"label": 1, "confidence": 0.9}
    assert rows[0]["prompt_hash"] == "0" * 64


def test_audit_log_off_mode_skips_insert(fake_crc, sqlite_conn):
    log = PromptAuditLogger(fake_crc, audit_level="off")
    ok = log.log(**_kwargs())
    assert ok is False
    assert _rows(sqlite_conn) == []
    assert log.audit_rows_written == 0


def test_audit_log_invalid_level_raises():
    with pytest.raises(ValueError):
        PromptAuditLogger(crc_ds=None, audit_level="loud")


def test_audit_log_db_failure_does_not_raise(monkeypatch, fake_crc):
    class Boom:
        def __enter__(self):
            raise RuntimeError("db kaboom")

        def __exit__(self, *a):
            return False

    log = PromptAuditLogger(Boom(), audit_level="full")
    ok = log.log(**_kwargs())
    assert ok is False
    assert log.audit_rows_written == 0


def test_audit_unknown_outcome_coerced_to_provider_error(fake_crc, sqlite_conn):
    log = PromptAuditLogger(fake_crc, audit_level="full")
    log.log(**_kwargs(guardrail_outcome="weird_outcome"))
    rows = _rows(sqlite_conn)
    assert rows[0]["guardrail_outcome"] == "provider_error"


def test_audit_records_token_counts(fake_crc, sqlite_conn):
    log = PromptAuditLogger(fake_crc, audit_level="full")
    log.log(**_kwargs(prompt_tokens=200, completion_tokens=80))
    rows = _rows(sqlite_conn)
    assert rows[0]["prompt_tokens"] == 200
    assert rows[0]["completion_tokens"] == 80


def test_audit_rows_written_counter_increments(fake_crc, sqlite_conn):
    log = PromptAuditLogger(fake_crc, audit_level="full")
    for _ in range(3):
        log.log(**_kwargs())
    assert log.audit_rows_written == 3
    assert len(_rows(sqlite_conn)) == 3


def test_audit_records_exhausted_outcome(fake_crc, sqlite_conn):
    log = PromptAuditLogger(fake_crc, audit_level="full")
    log.log(**_kwargs(guardrail_outcome="exhausted", response_text=None, parsed_output=None))
    rows = _rows(sqlite_conn)
    assert rows[0]["guardrail_outcome"] == "exhausted"


def test_audit_handles_null_parsed_output(fake_crc, sqlite_conn):
    log = PromptAuditLogger(fake_crc, audit_level="full")
    log.log(**_kwargs(parsed_output=None))
    rows = _rows(sqlite_conn)
    assert rows[0]["parsed_output"] is None


def test_audit_sql_is_schema_qualified_via_crc_db_name(monkeypatch, fake_crc, sqlite_conn):
    """H-5: the audit INSERT must include the ``$CRC_DB_NAME.`` schema prefix
    so it works without relying on the PG user's ``search_path`` configuration.

    Sets CRC_DB_NAME to a non-default value, wraps the translating cursor to
    capture SQL pre-translation, and asserts the production SQL contains the
    schema-qualified table name.
    """
    monkeypatch.setenv("CRC_DB_NAME", "test_schema_xyz")

    # Re-build the schema-prefix regex so the fake translator strips the new
    # prefix before forwarding to sqlite.
    import tests.LLM.conftest as _cf

    monkeypatch.setattr(_cf, "_SCHEMA_PREFIX_RE", _cf._build_schema_prefix_re())

    # Wrap the translating cursor's execute to capture SQL strings BEFORE
    # the prefix-stripping translator runs.
    captured: list = []
    original_translate = _cf._TranslatingCursor._translate

    def _spy_translate(sql):
        captured.append(sql)
        return original_translate(sql)

    monkeypatch.setattr(_cf._TranslatingCursor, "_translate", staticmethod(_spy_translate))

    log = PromptAuditLogger(fake_crc, audit_level="full")
    log.log(**_kwargs())

    assert captured, "no SQL captured by translator spy"
    qualified = [s for s in captured if "test_schema_xyz.llm_audit" in s]
    assert qualified, (
        f"audit SQL did not include the test_schema_xyz. prefix. Captured: {captured}"
    )


def test_audit_sql_works_with_empty_crc_db_name(monkeypatch, fake_crc, sqlite_conn):
    """If CRC_DB_NAME is unset/empty, fall back to unqualified table names.

    Documents that the schema-qualified form requires a configured schema.
    Empty CRC_DB_NAME → no prefix → unqualified SQL (legacy behavior).
    """
    monkeypatch.setenv("CRC_DB_NAME", "")
    log = PromptAuditLogger(fake_crc, audit_level="full")
    ok = log.log(**_kwargs())
    assert ok is True
    rows = _rows(sqlite_conn)
    assert len(rows) == 1
