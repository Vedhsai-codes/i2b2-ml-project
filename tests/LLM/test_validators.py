# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Tests for ``validators.structured_output`` and ``validators.hallucination_guard``."""
from __future__ import annotations

import pytest

from i2b2_cdi.LLM.validators import HallucinationGuard, SchemaValidator
from i2b2_cdi.LLM.validators.structured_output import coerce_text_to_dict


_SIMPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "integer", "enum": [0, 1]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence": {"type": "string"},
    },
    "required": ["label", "confidence"],
}


# ----------------------- coerce_text_to_dict -----------------------


def test_coerce_whole_text_parse():
    assert coerce_text_to_dict('{"a": 1}') == {"a": 1}


def test_coerce_xml_tag():
    assert coerce_text_to_dict('preamble <json>{"label": 1}</json> postamble') == {"label": 1}


def test_coerce_markdown_fence():
    txt = "Here is the answer:\n```json\n{\"label\": 0, \"confidence\": 0.8}\n```\n"
    assert coerce_text_to_dict(txt) == {"label": 0, "confidence": 0.8}


def test_coerce_widest_brace_block():
    txt = "garbage {\"label\": 1, \"confidence\": 0.9} trailing"
    assert coerce_text_to_dict(txt) == {"label": 1, "confidence": 0.9}


def test_coerce_returns_none_when_garbage():
    assert coerce_text_to_dict("no json here at all") is None


def test_coerce_returns_none_for_array():
    assert coerce_text_to_dict("[1, 2, 3]") is None


def test_coerce_handles_empty_and_none():
    assert coerce_text_to_dict("") is None
    assert coerce_text_to_dict(None) is None
    assert coerce_text_to_dict("   ") is None


def test_coerce_prefers_xml_over_fence():
    txt = '<json>{"a": 1}</json> ```json\n{"a": 2}\n```'
    assert coerce_text_to_dict(txt) == {"a": 1}


# ----------------------- SchemaValidator -----------------------


def test_schema_validator_accepts_valid_input():
    v = SchemaValidator(_SIMPLE_SCHEMA)
    ok, err = v.validate({"label": 1, "confidence": 0.8, "evidence": "EF 30%"})
    assert ok and err is None


def test_schema_validator_rejects_invalid_input():
    v = SchemaValidator(_SIMPLE_SCHEMA)
    ok, err = v.validate({"label": "yes", "confidence": 0.8})
    assert not ok
    assert "label" in err


def test_schema_validator_no_schema_always_ok():
    v = SchemaValidator(None)
    ok, err = v.validate({"anything": 1})
    assert ok and err is None


def test_schema_validator_bad_schema_raises_at_init():
    with pytest.raises(ValueError):
        SchemaValidator({"type": "not-a-type"})


def test_schema_validator_rejects_non_dict_schema():
    with pytest.raises(TypeError):
        SchemaValidator("oops")


def test_schema_validator_missing_required_field():
    v = SchemaValidator(_SIMPLE_SCHEMA)
    ok, err = v.validate({"label": 1})
    assert not ok
    assert "confidence" in err


# ----------------------- HallucinationGuard -----------------------


def test_guard_empty_config_passes_everything():
    g = HallucinationGuard({})
    ok, err = g.check({"anything": True}, source_note="n/a")
    assert ok and err is None


def test_guard_min_confidence_blocks_low_conf():
    g = HallucinationGuard({"min_confidence": 0.7})
    ok, err = g.check({"label": 1, "confidence": 0.5})
    assert not ok
    assert "confidence" in err


def test_guard_min_confidence_accepts_high_conf():
    g = HallucinationGuard({"min_confidence": 0.7})
    ok, err = g.check({"label": 1, "confidence": 0.95})
    assert ok and err is None


def test_guard_missing_confidence_field_when_required():
    g = HallucinationGuard({"min_confidence": 0.5})
    ok, err = g.check({"label": 1})
    assert not ok
    assert "confidence" in err


def test_guard_evidence_substring_case_insensitive_default():
    g = HallucinationGuard({"require_evidence_substring": True})
    note = "Patient has EF 30% per echo."
    ok, err = g.check({"label": 1, "evidence": "ef 30%"}, source_note=note)
    assert ok and err is None


def test_guard_evidence_substring_case_sensitive_optin():
    g = HallucinationGuard(
        {"require_evidence_substring": True, "case_sensitive_evidence": True}
    )
    note = "Patient has EF 30%."
    ok, err = g.check({"label": 1, "evidence": "ef 30%"}, source_note=note)
    assert not ok


def test_guard_evidence_missing_in_source_note():
    g = HallucinationGuard({"require_evidence_substring": True})
    note = "Patient has good blood pressure."
    ok, err = g.check({"label": 1, "evidence": "EF 30%"}, source_note=note)
    assert not ok
    assert "evidence" in err


def test_guard_evidence_missing_field():
    g = HallucinationGuard({"require_evidence_substring": True})
    ok, err = g.check({"label": 1}, source_note="anything")
    assert not ok


def test_guard_rejects_invalid_min_confidence_at_init():
    with pytest.raises(ValueError):
        HallucinationGuard({"min_confidence": 1.5})
    with pytest.raises(ValueError):
        HallucinationGuard({"min_confidence": -0.1})
    with pytest.raises(ValueError):
        HallucinationGuard({"min_confidence": "x"})


def test_guard_parsed_none_fails():
    g = HallucinationGuard({"min_confidence": 0.5})
    ok, err = g.check(None, source_note="x")
    assert not ok


def test_guard_negative_max_retries_rejected():
    with pytest.raises(ValueError):
        HallucinationGuard({"max_retries": -1})
