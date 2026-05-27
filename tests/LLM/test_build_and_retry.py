# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Tests for perform_LLM.build_llm_concept + run_label retry+guardrail behavior."""
from __future__ import annotations

import json

import pytest

from i2b2_cdi.LLM.apply_LLM import run_label
from i2b2_cdi.LLM.audit import PromptAuditLogger
from i2b2_cdi.LLM.perform_LLM import build_llm_concept
from i2b2_cdi.LLM.providers import register_provider, unregister_provider
from tests.LLM.fixtures.mock_provider import MockProvider


GOOD_BLOB = {
    "prompt_template": "cohort_labeling",
    "prompt_variables": {
        "condition": "heart failure",
        "definition": "EF < 40 or BNP > 400",
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
    "guardrails": {"min_confidence": 0.5, "max_retries": 1, "require_evidence_substring": False},
    "sampling": {"temperature": 0.0, "max_tokens": 128},
    "audit_level": "full",
}


@pytest.fixture(autouse=True)
def register_mock():
    register_provider("mock", MockProvider)
    yield
    unregister_provider("mock")


@pytest.fixture
def seeded_concept(sqlite_conn, seed_concept):
    seed_concept("HF_LLM", "/LLM/Diagnosis/HF_LLM", GOOD_BLOB)
    return "HF_LLM"


def test_build_concept_persists_augmented_blob(fake_crc, sqlite_conn, seeded_concept):
    augmented = build_llm_concept(crc_ds=fake_crc, concept_code=seeded_concept, concept_blob=GOOD_BLOB)
    assert "prompt_template_hash" in augmented
    assert augmented["provider_metadata"]["name"] == "mock"
    cur = sqlite_conn.cursor()
    cur.execute("SELECT concept_blob FROM concept_dimension WHERE concept_cd = ?", (seeded_concept,))
    stored = json.loads(cur.fetchone()[0])
    assert stored["prompt_template_hash"] == augmented["prompt_template_hash"]


def test_build_concept_missing_required_field_raises(fake_crc, seeded_concept):
    bad = dict(GOOD_BLOB)
    bad.pop("prompt_template")
    with pytest.raises(ValueError):
        build_llm_concept(crc_ds=fake_crc, concept_code=seeded_concept, concept_blob=bad)


def test_build_concept_bad_schema_raises(fake_crc, seeded_concept):
    bad = dict(GOOD_BLOB)
    bad["output_schema"] = {"type": "not-a-type"}
    with pytest.raises(ValueError):
        build_llm_concept(crc_ds=fake_crc, concept_code=seeded_concept, concept_blob=bad)


def test_build_concept_health_check_failure_raises(fake_crc, seeded_concept, monkeypatch):
    class _BadHealth(MockProvider):
        def health_check(self):
            return False

    register_provider("mock_bad", _BadHealth)
    try:
        bad = dict(GOOD_BLOB)
        bad["provider"] = {"name": "mock_bad", "model": "x"}
        with pytest.raises(RuntimeError):
            build_llm_concept(crc_ds=fake_crc, concept_code=seeded_concept, concept_blob=bad)
    finally:
        unregister_provider("mock_bad")


@pytest.fixture
def cohort_one_patient(sqlite_conn, seed_concept, seed_patient_notes):
    seed_concept("target_one", "/cohort/single", {"x": 1})
    sqlite_conn.execute(
        "INSERT INTO observation_fact (patient_num, concept_cd, start_date, observation_blob) "
        "VALUES (?, ?, ?, ?)",
        (501, "target_one", "2018-01-01", "n/a"),
    )
    sqlite_conn.commit()
    seed_patient_notes(501, "/MIMIC/notes/discharge", "Patient has acute symptoms.")


def _captured_send():
    box = {}

    def send(df):
        box["df"] = df

    return box, send


def test_run_label_retries_on_schema_invalid_and_then_succeeds(fake_crc, cohort_one_patient):
    """First attempt returns invalid schema, second uses canned valid response."""
    box, send = _captured_send()
    audit = PromptAuditLogger(fake_crc, audit_level="full")

    class _Flaky(MockProvider):
        def __init__(self, **kw):
            super().__init__(**kw)
            self._n = 0

        def generate(self, prompt, **kw):
            self._n += 1
            if self._n == 1:
                return self._wrap('<json>{"label": "bad", "confidence": 0.9}</json>')
            return self._wrap('<json>{"label": 1, "confidence": 0.95, "evidence": "x"}</json>')

    blob = dict(GOOD_BLOB)
    blob["guardrails"] = dict(blob["guardrails"])
    blob["guardrails"]["max_retries"] = 2
    out = run_label(
        conceptPath="/LLM/X",
        conceptCode="HF_LLM",
        crc_ds=fake_crc,
        job_id=1,
        project_name="p",
        concept_blob=blob,
        input_params={"target_patient_set": ["/cohort/single"]},
        send_facts=send,
        provider=_Flaky(),
        audit_logger=audit,
    )
    assert out["n_processed"] == 1
    assert out["n_failed_validation"] == 0
    assert out["n_labeled_positive"] == 1
    assert audit.audit_rows_written >= 2  # one per attempt


def test_run_label_exhausts_writes_extra_exhausted_row(fake_crc, cohort_one_patient, sqlite_conn):
    box, send = _captured_send()
    audit = PromptAuditLogger(fake_crc, audit_level="full")

    blob = dict(GOOD_BLOB)
    blob["guardrails"] = dict(blob["guardrails"])
    blob["guardrails"]["max_retries"] = 1

    out = run_label(
        conceptPath="/LLM/X",
        conceptCode="HF_LLM",
        crc_ds=fake_crc,
        job_id=2,
        project_name="p",
        concept_blob=blob,
        input_params={"target_patient_set": ["/cohort/single"]},
        send_facts=send,
        provider=MockProvider(fail_mode="schema_invalid"),
        audit_logger=audit,
    )
    assert out["n_failed_validation"] == 1
    cur = sqlite_conn.cursor()
    cur.execute(
        "SELECT guardrail_outcome FROM llm_audit WHERE job_id = ? ORDER BY audit_id",
        (2,),
    )
    outcomes = [r[0] for r in cur.fetchall()]
    assert "exhausted" in outcomes


def test_run_label_low_confidence_blocks_label(fake_crc, cohort_one_patient):
    _, send = _captured_send()
    blob = dict(GOOD_BLOB)
    blob["guardrails"] = {"min_confidence": 0.8, "max_retries": 0, "require_evidence_substring": False}
    out = run_label(
        conceptPath="/LLM/X",
        conceptCode="HF_LLM",
        crc_ds=fake_crc,
        job_id=3,
        project_name="p",
        concept_blob=blob,
        input_params={"target_patient_set": ["/cohort/single"]},
        send_facts=send,
        provider=MockProvider(fail_mode="low_confidence"),
    )
    assert out["n_failed_validation"] == 1
    assert out["n_labeled_positive"] == 0


def test_run_label_hallucination_blocked_by_guard(fake_crc, cohort_one_patient):
    _, send = _captured_send()
    blob = dict(GOOD_BLOB)
    blob["guardrails"] = {
        "min_confidence": 0.0,
        "require_evidence_substring": True,
        "max_retries": 0,
    }
    out = run_label(
        conceptPath="/LLM/X",
        conceptCode="HF_LLM",
        crc_ds=fake_crc,
        job_id=4,
        project_name="p",
        concept_blob=blob,
        input_params={"target_patient_set": ["/cohort/single"]},
        send_facts=send,
        provider=MockProvider(fail_mode="hallucinate"),
    )
    assert out["n_failed_validation"] == 1


# ---------------------------------------------------------------------------
# H-4: prediction_event_path → real start_date (with time_buffer days)
# ---------------------------------------------------------------------------


@pytest.fixture
def cohort_one_patient_with_event(sqlite_conn, seed_concept, seed_patient_notes):
    """Seed a single patient with both a note AND a prediction event."""
    seed_concept("target_one", "/cohort/single", {"x": 1})
    seed_concept("HF_EVENT", "/MIMIC/events/hf_admit", {})
    # Patient is in the cohort
    sqlite_conn.execute(
        "INSERT INTO observation_fact (patient_num, concept_cd, start_date, observation_blob) "
        "VALUES (?, ?, ?, ?)",
        (501, "target_one", "2018-01-01", "n/a"),
    )
    # Patient has a discharge note
    seed_patient_notes(501, "/MIMIC/notes/discharge", "Patient has EF 30%.")
    # Patient has a clinical event at a known date — this is what start_date
    # should resolve to (minus time_buffer).
    sqlite_conn.execute(
        "INSERT INTO observation_fact (patient_num, concept_cd, start_date, observation_blob) "
        "VALUES (?, ?, ?, ?)",
        (501, "HF_EVENT", "2018-06-15 09:30:00", ""),
    )
    sqlite_conn.commit()


def test_apply_label_uses_prediction_event_date_when_provided(
    fake_crc, cohort_one_patient_with_event
):
    """H-4: start_date should be the event date minus time_buffer days, NOT _today()."""
    captured, send = _captured_send()
    blob = dict(GOOD_BLOB)
    blob["prediction_event_path"] = ["/MIMIC/events/hf_admit"]
    blob["time_buffer"] = 30  # days
    out = run_label(
        conceptPath="/LLM/X",
        conceptCode="HF_LLM",
        crc_ds=fake_crc,
        job_id=10,
        project_name="p",
        concept_blob=blob,
        input_params={"target_patient_set": ["/cohort/single"]},
        send_facts=send,
        provider=MockProvider(canned_response={"label": 1, "confidence": 0.9, "evidence": "EF 30%"}),
    )
    assert out["n_processed"] == 1
    assert out["n_labeled_positive"] == 1
    # Event was 2018-06-15; minus 30 days = 2018-05-16
    df = captured["df"]
    assert len(df) == 1
    start_date = df.iloc[0]["start-date"]
    assert start_date.startswith("2018-05-16"), (
        f"expected event-date - 30d (2018-05-16); got {start_date!r}"
    )


def test_apply_label_warns_when_event_path_missing(
    fake_crc, cohort_one_patient, caplog
):
    """H-4: when prediction_event_path absent, log a WARNING and fall back to _today()."""
    import logging as _logging

    caplog.set_level(_logging.WARNING)

    captured, send = _captured_send()
    # blob has NO prediction_event_path
    blob = dict(GOOD_BLOB)
    blob.pop("prediction_event_path", None)
    blob.pop("prediction_event_paths", None)
    out = run_label(
        conceptPath="/LLM/X",
        conceptCode="HF_LLM",
        crc_ds=fake_crc,
        job_id=11,
        project_name="p",
        concept_blob=blob,
        input_params={"target_patient_set": ["/cohort/single"]},
        send_facts=send,
        provider=MockProvider(canned_response={"label": 1, "confidence": 0.9, "evidence": "x"}),
    )
    assert out["n_labeled_positive"] == 1
    # start_date falls back to today
    df = captured["df"]
    start_date = df.iloc[0]["start-date"]
    from datetime import datetime, timezone as _tz

    today_prefix = datetime.now(_tz.utc).strftime("%Y-%m-%d")
    assert start_date.startswith(today_prefix), (
        f"expected today's date prefix {today_prefix}; got {start_date!r}"
    )
