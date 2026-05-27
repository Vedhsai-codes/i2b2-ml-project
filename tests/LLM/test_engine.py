# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Tests for the LLM engine dispatch + run_label end-to-end with mocks."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from i2b2_cdi.LLM.apply_LLM import run_label
from i2b2_cdi.LLM.audit import PromptAuditLogger
from i2b2_cdi.LLM.llm_usecase import dispatch_usecase
from i2b2_cdi.LLM.providers import register_provider, unregister_provider
from tests.LLM.fixtures.mock_provider import MockProvider


@pytest.fixture(autouse=True)
def _register_mock():
    register_provider("mock", MockProvider)
    yield
    unregister_provider("mock")


BLOB = {
    "target_patient_set": ["/cohort/target"],
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
    "guardrails": {
        "min_confidence": 0.5,
        "require_evidence_substring": False,
        "max_retries": 1,
    },
    "sampling": {"temperature": 0.0, "max_tokens": 256},
    "audit_level": "full",
}


@pytest.fixture
def seed_cohort(sqlite_conn, seed_concept, seed_patient_notes):
    seed_concept(
        "target", "/cohort/target", {"members": "ok"},
    )
    sqlite_conn.execute(
        "INSERT INTO observation_fact (patient_num, concept_cd, start_date, observation_blob) "
        "VALUES (?, ?, ?, ?)",
        (101, "target", "2018-01-01", "n/a"),
    )
    sqlite_conn.execute(
        "INSERT INTO observation_fact (patient_num, concept_cd, start_date, observation_blob) "
        "VALUES (?, ?, ?, ?)",
        (102, "target", "2018-01-01", "n/a"),
    )
    sqlite_conn.commit()
    seed_patient_notes(101, "/MIMIC/notes/discharge", "Patient has EF 30% and BNP 1800.")
    seed_patient_notes(102, "/MIMIC/notes/discharge", "Patient with normal ejection fraction.")


def _captured_send_facts():
    captured: dict = {}

    def _send(df: pd.DataFrame):
        captured["df"] = df

    return captured, _send


def test_dispatch_routes_llm_label(fake_crc, seed_cohort):
    captured, send = _captured_send_facts()
    out = dispatch_usecase(
        jobType="llm-label",
        conceptPath="/LLM/Diagnosis/HF_LLM",
        conceptCode="HF_LLM",
        crc_ds=fake_crc,
        job_id=1,
        project_name="i2b2demodata",
        concept_blob=BLOB,
        input_params={},
        send_facts=send,
    )
    assert isinstance(out, dict)
    assert set(out.keys()) >= {"n_processed", "n_labeled_positive", "n_failed_validation",
                                "mean_confidence", "total_cost_usd", "total_latency_s",
                                "audit_rows_written"}


def test_dispatch_routes_bare_llm(fake_crc, seed_cohort):
    captured, send = _captured_send_facts()
    out = dispatch_usecase(
        jobType="llm",
        conceptPath="/LLM/X",
        conceptCode="HF_LLM",
        crc_ds=fake_crc,
        job_id=1,
        project_name="i2b2demodata",
        concept_blob=BLOB,
        input_params={},
        send_facts=send,
    )
    assert isinstance(out, dict)


def test_dispatch_extract_raises_notimplemented(fake_crc):
    _, send = _captured_send_facts()
    with pytest.raises(NotImplementedError):
        dispatch_usecase(
            jobType="llm-extract",
            conceptPath="/x",
            conceptCode="x",
            crc_ds=fake_crc,
            job_id=1,
            project_name="p",
            concept_blob=BLOB,
            input_params={},
            send_facts=send,
        )


def test_dispatch_feature_raises_notimplemented(fake_crc):
    _, send = _captured_send_facts()
    with pytest.raises(NotImplementedError):
        dispatch_usecase(
            jobType="llm-feature",
            conceptPath="/x",
            conceptCode="x",
            crc_ds=fake_crc,
            job_id=1,
            project_name="p",
            concept_blob=BLOB,
            input_params={},
            send_facts=send,
        )


def test_dispatch_unknown_suffix_raises_value_error(fake_crc):
    _, send = _captured_send_facts()
    with pytest.raises(ValueError):
        dispatch_usecase(
            jobType="llm-banana",
            conceptPath="/x",
            conceptCode="x",
            crc_ds=fake_crc,
            job_id=1,
            project_name="p",
            concept_blob=BLOB,
            input_params={},
            send_facts=send,
        )


def test_run_label_iterates_target_and_calls_send_facts(fake_crc, seed_cohort):
    captured, send = _captured_send_facts()
    audit = PromptAuditLogger(fake_crc, audit_level="full")
    mock = MockProvider(canned_response={"label": 1, "confidence": 0.9, "evidence": "EF"})
    out = run_label(
        conceptPath="/LLM/X",
        conceptCode="HF_LLM",
        crc_ds=fake_crc,
        job_id=7,
        project_name="i2b2demodata",
        concept_blob=BLOB,
        input_params={},
        send_facts=send,
        provider=mock,
        audit_logger=audit,
    )
    assert out["n_processed"] == 2
    assert "df" in captured
    df = captured["df"]
    assert list(df.columns) == ["mrn", "code", "start-date", "value"]
    assert set(df["mrn"].tolist()) == {101, 102}


def test_run_label_populates_summary_keys(fake_crc, seed_cohort):
    _, send = _captured_send_facts()
    mock = MockProvider(canned_response={"label": 1, "confidence": 0.9, "evidence": "x"})
    out = run_label(
        conceptPath="/LLM/X",
        conceptCode="HF_LLM",
        crc_ds=fake_crc,
        job_id=1,
        project_name="p",
        concept_blob=BLOB,
        input_params={},
        send_facts=send,
        provider=mock,
    )
    assert out["n_labeled_positive"] == 2
    assert out["n_failed_validation"] == 0
    assert out["audit_rows_written"] >= 2
    assert out["mean_confidence"] > 0.0


def test_run_label_no_patients_returns_zero_summary(fake_crc):
    _, send = _captured_send_facts()
    mock = MockProvider()
    out = run_label(
        conceptPath="/LLM/X",
        conceptCode="HF_LLM",
        crc_ds=fake_crc,
        job_id=1,
        project_name="p",
        concept_blob=BLOB,
        input_params={},
        send_facts=send,
        provider=mock,
    )
    assert out["n_processed"] == 0
    assert out["n_labeled_positive"] == 0
