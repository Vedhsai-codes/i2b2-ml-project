# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Tests for MockProvider behavior + factory + base LLMResponse contract."""
from __future__ import annotations

import pytest

from i2b2_cdi.LLM.providers import get_provider, register_provider, unregister_provider
from i2b2_cdi.LLM.providers.base import LLMResponse
from tests.LLM.fixtures.mock_provider import FAIL_MODES, MockProvider


@pytest.fixture
def register_mock():
    register_provider("mock", MockProvider)
    yield
    unregister_provider("mock")


def test_mock_provider_generate_happy_path():
    p = MockProvider()
    r = p.generate("hello world")
    assert isinstance(r, LLMResponse)
    assert "<json>" in r.text


def test_mock_provider_deterministic_for_same_prompt():
    p1 = MockProvider()
    p2 = MockProvider()
    r1 = p1.generate("identical prompt")
    r2 = p2.generate("identical prompt")
    assert r1.text == r2.text


def test_mock_provider_call_count_increments():
    p = MockProvider()
    p.generate("a")
    p.generate("b")
    p.generate("c")
    assert p.call_count == 3


def test_mock_provider_records_last_prompt():
    p = MockProvider()
    p.generate("inspect me")
    assert p.last_prompt == "inspect me"


def test_mock_provider_unknown_fail_mode_rejected():
    with pytest.raises(ValueError):
        MockProvider(fail_mode="banana")


@pytest.mark.parametrize("mode", list(FAIL_MODES))
def test_mock_provider_each_fail_mode_constructs(mode):
    p = MockProvider(fail_mode=mode)
    if mode == "timeout":
        with pytest.raises(TimeoutError):
            p.generate("x")
    elif mode == "empty":
        r = p.generate("x")
        assert r.text == ""
    else:
        r = p.generate("x")
        assert isinstance(r, LLMResponse)


def test_mock_provider_canned_response():
    p = MockProvider(canned_response={"label": 1, "confidence": 0.99, "evidence": "EF 25%"})
    r = p.generate("note")
    assert "0.99" in r.text


def test_mock_provider_health_check_true():
    assert MockProvider().health_check() is True


def test_get_provider_via_registry_resolves_mock(register_mock):
    p = get_provider({"name": "mock", "model": "mock-1"})
    assert isinstance(p, MockProvider)
    assert p.model == "mock-1"


def test_llm_response_default_usage_shape():
    r = LLMResponse(text="x")
    assert "prompt_tokens" in r.usage
    assert "completion_tokens" in r.usage
    assert "total_tokens" in r.usage


def test_llm_response_cost_defaults_to_zero():
    r = LLMResponse(text="x")
    assert r.cost_usd == 0.0
