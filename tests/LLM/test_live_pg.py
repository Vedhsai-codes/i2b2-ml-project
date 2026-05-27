# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""End-to-end smoke tests against a real Postgres + jobWatcher.

These tests are **auto-deselected** unless BOTH:

    1. environment variable ``RUN_LIVE_PG=1`` is set
    2. the ``docker`` binary is on PATH

When either prerequisite is unmet, ``conftest.pytest_collection_modifyitems``
removes them from the test plan entirely. ``pytest -m live_pg`` will then
collect zero items.

To run:

    docker-compose up -d
    psql -U i2b2 -d i2b2demodata -f deployment/pg/100_llm_audit.sql
    RUN_LIVE_PG=1 python -m pytest tests/LLM/test_live_pg.py -v

These tests use ``MockProvider`` so they exercise the i2b2 plumbing
(orchestrator → engine → audit → observation_fact) without hitting any real
LLM endpoint. Real-provider validation is a separate manual smoke documented
in CHANGES.md §7.
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

import pytest


pytestmark = pytest.mark.live_pg


def _required_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        pytest.fail(
            f"live_pg test requires env var {name}. "
            f"Typical values for the bundled docker-compose: "
            f"CRC_DB_HOST=localhost CRC_DB_PORT=5432 CRC_DB_USER=i2b2 "
            f"CRC_DB_PASS=demouser CRC_DB_NAME=i2b2demodata"
        )
    return val


@pytest.fixture(scope="module")
def live_pg_conn():
    """Open a real psycopg2 connection. Fails the suite cleanly if anything is off."""
    try:
        import psycopg2  # type: ignore
    except ImportError as e:
        pytest.fail(
            f"psycopg2 not installed in this venv ({e!r}). "
            f"Install with `pip install psycopg2-binary` (already pinned in requirements.txt)."
        )

    try:
        conn = psycopg2.connect(
            host=_required_env("CRC_DB_HOST"),
            port=int(os.environ.get("CRC_DB_PORT", "5432")),
            user=_required_env("CRC_DB_USER"),
            password=_required_env("CRC_DB_PASS"),
            dbname=_required_env("CRC_DB_NAME"),
            connect_timeout=5,
        )
    except Exception as e:
        pytest.fail(
            f"Could not connect to live Postgres: {e!r}. "
            f"Is docker-compose up? Is Docker Desktop running?"
        )
    conn.autocommit = True
    yield conn
    conn.close()


def test_live_pg_llm_audit_table_exists(live_pg_conn):
    """The 100_llm_audit migration must be applied before any LLM job runs.

    This test proves the migration succeeded by selecting against the table
    schema. Failure here means: run ``psql -f deployment/pg/100_llm_audit.sql``.
    """
    with live_pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'llm_audit'
            ORDER BY ordinal_position
            """
        )
        rows = cur.fetchall()
    columns = {r[0] for r in rows}
    expected = {
        "audit_id", "job_id", "patient_num", "concept_cd",
        "provider_name", "model_name", "prompt_hash",
        "prompt_text", "response_text", "parsed_output",
        "finish_reason", "prompt_tokens", "completion_tokens",
        "cost_usd", "latency_ms", "guardrail_outcome", "created_at",
    }
    missing = expected - columns
    assert not missing, f"llm_audit schema missing columns: {missing}"


def test_live_pg_llmengine_glob_discovery(live_pg_conn):
    """Verify the jobOrchestrator's glob discovery picks up llmEngine.py.

    This duplicates the inspection in CHANGES.md §5 criterion #1 but uses
    the actual jobOrchestrator code path, which proves the import works
    against the live env (real psycopg2, real Postgres).
    """
    from i2b2_cdi.job.jobOrchestrator import jobOrchestrator

    executor = jobOrchestrator()
    module_names = [
        m.split("/")[-1].replace("Engine.py", "").lower()
        for m in executor.engineModules
    ]
    assert "llm" in module_names, (
        f"llmEngine.py not discovered by jobOrchestrator; "
        f"saw modules: {module_names}"
    )


def test_live_pg_full_label_job_end_to_end(live_pg_conn):
    """The §2.10 #4 criterion: status transitions PENDING → PROCESSING → COMPLETED.

    Submits a real job row, polls until completion, and verifies
    observation_fact + llm_audit populated. Uses MockProvider so no real
    LLM endpoint is touched.
    """
    from i2b2_cdi.LLM.providers import register_provider, unregister_provider
    from tests.LLM.fixtures.mock_provider import MockProvider

    register_provider("mock", MockProvider)
    try:
        with live_pg_conn.cursor() as cur:
            cur.execute("SELECT 1 FROM concept_dimension LIMIT 1")
            assert cur.fetchone() is not None, (
                "concept_dimension is empty — run the standard i2b2 demo loader first"
            )

            concept_blob = {
                "target_patient_set": ["/cohort/demo"],
                "note_concept_paths": ["/MIMIC/notes/discharge"],
                "prompt_template": "cohort_labeling",
                "prompt_variables": {
                    "condition": "heart failure",
                    "definition": "EF < 40% or BNP > 400",
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "integer", "enum": [0, 1]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "evidence": {"type": "string"},
                    },
                    "required": ["label", "confidence"],
                },
                "provider": {"name": "mock", "model": "mock-1"},
                "guardrails": {"min_confidence": 0.5, "max_retries": 1},
                "sampling": {"temperature": 0.0, "max_tokens": 128},
                "audit_level": "full",
            }
            cur.execute(
                "INSERT INTO concept_dimension (concept_cd, concept_path, name_char, concept_blob, definition_type) "
                "VALUES ('LIVE_PG_HF', '/LLM/Diagnosis/LIVE_PG_HF', 'LIVE_PG_HF', %s, 'LLM-BUILD') "
                "ON CONFLICT (concept_cd) DO UPDATE SET concept_blob = EXCLUDED.concept_blob",
                (json.dumps(concept_blob),),
            )

            cur.execute(
                "INSERT INTO job (project_name, priority, input, status, job_type, started_on, completed_on) "
                "VALUES (%s, %s, %s, 'PENDING', %s, NOW(), NOW()) RETURNING id",
                (
                    _required_env("CRC_DB_NAME"),
                    0,
                    json.dumps({"path": "/LLM/Diagnosis/LIVE_PG_HF"}),
                    "llm-label",
                ),
            )
            job_id = cur.fetchone()[0]

        deadline = time.time() + 45
        final_status: Optional[str] = None
        while time.time() < deadline:
            with live_pg_conn.cursor() as cur:
                cur.execute("SELECT status FROM job WHERE id = %s", (job_id,))
                row = cur.fetchone()
            if row and row[0] in ("COMPLETED", "ERROR"):
                final_status = row[0]
                break
            time.sleep(2)
        assert final_status == "COMPLETED", (
            f"Job {job_id} did not reach COMPLETED within 45s. Final status: {final_status!r}. "
            f"Is the jobWatcher daemon running?"
        )

        with live_pg_conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM llm_audit WHERE job_id = %s", (job_id,)
            )
            audit_count = cur.fetchone()[0]
            cur.execute(
                "SELECT count(*) FROM observation_fact WHERE concept_cd = 'LIVE_PG_HF'"
            )
            fact_count = cur.fetchone()[0]
            cur.execute(
                "SELECT output FROM job WHERE id = %s", (job_id,)
            )
            job_output_raw = cur.fetchone()[0]
        assert audit_count > 0, "llm_audit has no rows for this job"
        assert fact_count > 0, "observation_fact has no rows under LIVE_PG_HF"
        assert job_output_raw, "job.output is empty after COMPLETED"
        output_dict = json.loads(job_output_raw.replace("'", '"'))
        for key in (
            "n_processed",
            "n_labeled_positive",
            "n_failed_validation",
            "mean_confidence",
            "total_cost_usd",
            "total_latency_s",
            "audit_rows_written",
        ):
            assert key in output_dict, f"job.output missing key {key!r}"
    finally:
        unregister_provider("mock")
