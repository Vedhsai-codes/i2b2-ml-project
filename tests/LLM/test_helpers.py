# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Tests for ``llm_helper``: render_prompt, chunk_notes, retry_with_backoff, hash."""
from __future__ import annotations

import pytest

from i2b2_cdi.LLM.llm_helper import (
    RetryableValidationError,
    chunk_notes,
    compute_prompt_hash,
    render_prompt,
    retry_with_backoff,
)


def test_render_prompt_renders_known_template():
    out = render_prompt(
        "cohort_labeling",
        {"condition": "diabetes", "definition": "HbA1c > 6.5", "note_text": "A1c 7.2"},
    )
    assert "diabetes" in out
    assert "HbA1c" in out
    assert "A1c 7.2" in out


def test_render_prompt_strict_undefined_missing_var():
    with pytest.raises(Exception):  # jinja2.UndefinedError subclass
        render_prompt("cohort_labeling", {"condition": "X"})


def test_render_prompt_unknown_template_raises_filenotfound():
    with pytest.raises(FileNotFoundError):
        render_prompt("does_not_exist", {})


def test_render_prompt_with_or_without_dot_txt_match():
    a = render_prompt(
        "cohort_labeling",
        {"condition": "x", "definition": "y", "note_text": "z"},
    )
    b = render_prompt(
        "cohort_labeling.txt",
        {"condition": "x", "definition": "y", "note_text": "z"},
    )
    assert a == b


def test_compute_prompt_hash_is_sha256_hex():
    h = compute_prompt_hash("hello")
    assert isinstance(h, str)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_compute_prompt_hash_is_deterministic():
    assert compute_prompt_hash("abc") == compute_prompt_hash("abc")
    assert compute_prompt_hash("abc") != compute_prompt_hash("abd")


def test_chunk_notes_empty():
    assert chunk_notes("", 100) == []
    assert chunk_notes("   ", 100) == []


def test_chunk_notes_short_text_one_chunk():
    out = chunk_notes("This is a short note.", 100)
    assert len(out) == 1
    assert "short note" in out[0]


def test_chunk_notes_many_sentences_multiple_chunks():
    txt = " ".join([f"Sentence {i}." for i in range(40)])
    out = chunk_notes(txt, max_tokens=10)
    assert len(out) > 1
    for chunk in out:
        assert chunk


def test_chunk_notes_single_long_sentence_hard_cut():
    txt = "x" * 2000
    out = chunk_notes(txt, max_tokens=50)
    assert len(out) > 1
    assert all(len(c) <= 50 * 4 for c in out)


def test_chunk_notes_zero_budget_raises():
    with pytest.raises(ValueError):
        chunk_notes("hello", 0)


def test_retry_with_backoff_returns_immediately_on_success():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return "ok"

    out = retry_with_backoff(fn, max_retries=3, base_delay_s=0.0)
    assert out == "ok"
    assert calls["n"] == 1


def test_retry_with_backoff_retries_then_succeeds():
    state = {"n": 0}

    def fn():
        state["n"] += 1
        if state["n"] < 3:
            raise TimeoutError("transient")
        return "after retries"

    out = retry_with_backoff(fn, max_retries=3, base_delay_s=0.0)
    assert out == "after retries"
    assert state["n"] == 3


def test_retry_with_backoff_exhausts_and_reraises():
    state = {"n": 0}

    def fn():
        state["n"] += 1
        raise ConnectionError("always")

    with pytest.raises(ConnectionError):
        retry_with_backoff(fn, max_retries=2, base_delay_s=0.0)
    assert state["n"] == 3  # 1 initial + 2 retries


def test_retry_with_backoff_does_not_retry_non_listed_exception():
    state = {"n": 0}

    def fn():
        state["n"] += 1
        raise ValueError("config bug")

    with pytest.raises(ValueError):
        retry_with_backoff(fn, max_retries=5, base_delay_s=0.0)
    assert state["n"] == 1  # no retries


def test_retry_with_backoff_retries_on_retryable_validation():
    state = {"n": 0}

    def fn():
        state["n"] += 1
        if state["n"] < 2:
            raise RetryableValidationError("bad schema")
        return "good"

    out = retry_with_backoff(fn, max_retries=3, base_delay_s=0.0)
    assert out == "good"


def test_retry_with_backoff_calls_sleep_with_exponential_delays():
    state = {"n": 0, "sleeps": []}

    def fn():
        state["n"] += 1
        raise TimeoutError("again")

    def fake_sleep(s):
        state["sleeps"].append(s)

    with pytest.raises(TimeoutError):
        retry_with_backoff(
            fn,
            max_retries=3,
            base_delay_s=1.0,
            max_delay_s=10.0,
            sleep=fake_sleep,
        )
    assert state["sleeps"] == [1.0, 2.0, 4.0]


def test_retry_with_backoff_negative_max_retries_raises():
    with pytest.raises(ValueError):
        retry_with_backoff(lambda: "x", max_retries=-1, base_delay_s=0.0)
