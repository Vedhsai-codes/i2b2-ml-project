# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Tests for ``evaluation.run_demonstration``.

These tests verify the eval harness end-to-end on the checked-in
synthetic cohort using MockProvider variants — no real LLM, no network,
no live i2b2 Postgres. The eval module is exercised as a library
(``evaluation.run_demonstration.run`` is called directly).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import types
from pathlib import Path

import pandas as pd
import pytest


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Stub i2b2 native deps the same way tests/LLM/conftest.py does — the eval
# harness imports i2b2_cdi.LLM transitively, which pulls psycopg2 / Mozilla
# / pyodbc / tabulate. Keep this LOCAL to the eval test package so it
# doesn't bleed into other tests.
# ---------------------------------------------------------------------------

import i2b2_cdi  # noqa: E402  -- ensure the real package is in sys.modules first

for _stub in ("psycopg2", "pyodbc"):
    if _stub not in sys.modules:
        _m = types.ModuleType(_stub)
        _m.Error = type("Error", (Exception,), {})
        sys.modules[_stub] = _m

if "Mozilla" not in sys.modules:
    sys.modules["Mozilla"] = types.ModuleType("Mozilla")
    sys.modules["Mozilla.exception"] = types.ModuleType("Mozilla.exception")
    _err_mod = types.ModuleType("Mozilla.exception.mozilla_cdi_database_error")
    _err_mod.MozillaCdiDatabaseError = type("MozillaCdiDatabaseError", (Exception,), {})
    sys.modules["Mozilla.exception.mozilla_cdi_database_error"] = _err_mod


COHORT_CSV = _PROJECT_ROOT / "evaluation" / "synthetic_cohort.csv"
SAMPLE_CONFIG = _PROJECT_ROOT / "evaluation" / "sample_config.json"


@pytest.fixture
def out_root(tmp_path):
    p = tmp_path / "results"
    p.mkdir()
    return p


@pytest.fixture(autouse=True)
def _register_eval_mock():
    """Reset PROVIDER_REGISTRY between tests so a 'mock' entry doesn't leak."""
    from i2b2_cdi.LLM.providers import PROVIDER_REGISTRY, unregister_provider

    pre = "mock" in PROVIDER_REGISTRY
    yield
    if not pre and "mock" in PROVIDER_REGISTRY:
        unregister_provider("mock")


def _load_metrics(results_dir: Path) -> dict:
    return json.loads((results_dir / "metrics_summary.json").read_text())


# ---------------------------------------------------------------------------
# Test 1 — smoke: all 6 expected output files appear; metrics are sane.
# ---------------------------------------------------------------------------


def test_run_demonstration_smoke(out_root):
    from evaluation.run_demonstration import run

    results_dir = run(
        cohort_path=COHORT_CSV,
        config_path=SAMPLE_CONFIG,
        out_root=out_root,
    )
    assert results_dir.exists()
    expected = {
        "raw_predictions.csv",
        "metrics_summary.json",
        "confusion_matrix.csv",
        "error_analysis.csv",
        "run_config.json",
        "run_log.txt",
    }
    actually_present = {p.name for p in results_dir.iterdir()}
    assert expected.issubset(actually_present), f"missing: {expected - actually_present}"

    metrics = _load_metrics(results_dir)
    # The synthetic cohort is 50 rows, half HF+. EvalMockProvider's heuristic
    # gives kappa > 0.8 in practice — we assert a loose lower bound so the
    # test isn't brittle to small mock-heuristic changes.
    assert metrics["n_total"] == 50
    assert metrics["n_failed"] == 0
    assert metrics["cohen_kappa"] >= 0.7, f"kappa too low: {metrics['cohen_kappa']}"


# ---------------------------------------------------------------------------
# Test 2 — metrics correctness: feed a known-truth fixture, assert kappa.
# ---------------------------------------------------------------------------


def _make_canned_cohort(tmp_path: Path, rows: list[dict]) -> Path:
    df = pd.DataFrame(rows)
    p = tmp_path / "canned_cohort.csv"
    df.to_csv(p, index=False)
    return p


def _make_canned_config(tmp_path: Path, provider: dict) -> Path:
    cfg = {
        "prompt_template": "cohort_labeling",
        "prompt_variables": {
            "condition": "heart failure",
            "definition": "EF < 40% or BNP > 400 pg/mL",
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "integer", "enum": [0, 1]},
                "confidence": {"type": "number"},
                "evidence": {"type": "string"},
            },
            "required": ["label", "confidence"],
        },
        "provider": provider,
        "guardrails": {"min_confidence": 0.0, "require_evidence_substring": False, "max_retries": 0},
        "sampling": {"temperature": 0.0, "max_tokens": 64},
        "audit_level": "full",
    }
    p = tmp_path / "canned_config.json"
    p.write_text(json.dumps(cfg))
    return p


from i2b2_cdi.LLM.providers.base import LLMProvider, LLMResponse


class _PerfectScoreProvider(LLMProvider):
    """Always returns the gold label; cohen_kappa should be exactly 1.0."""

    name = "perfect_mock"
    is_external = False
    model = "perfect-v1"

    def __init__(self, **_):
        pass

    def generate(self, prompt, *, max_tokens=512, temperature=0.0, output_schema=None, timeout_s=60):
        # The cohort row's hf_gold is embedded in the rendered prompt's note
        # text via test setup below; we detect it by a marker we control.
        if "HF_GOLD_IS_1" in prompt:
            body = '{"label": 1, "confidence": 0.99, "evidence": "marker"}'
        else:
            body = '{"label": 0, "confidence": 0.99, "evidence": "marker"}'
        return LLMResponse(
            text=f"<json>{body}</json>",
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            latency_ms=0,
            cost_usd=0.0,
            raw={},
        )

    def health_check(self):
        return True


def test_metrics_are_correct(tmp_path, out_root):
    """Feed a 4-row cohort with KNOWN predictions; assert kappa is exactly 1.0
    (all predictions match gold) and the confusion matrix is correctly shaped."""
    from i2b2_cdi.LLM.providers import register_provider, unregister_provider

    register_provider("perfect_mock", _PerfectScoreProvider)
    try:
        cohort_path = _make_canned_cohort(
            tmp_path,
            [
                {
                    "subject_id": 1, "hadm_id": 1, "note_id": "A",
                    "note_date": "2018-01-01",
                    "text": "Patient with HF. HF_GOLD_IS_1.",
                    "hf_gold": 1,
                },
                {
                    "subject_id": 2, "hadm_id": 2, "note_id": "B",
                    "note_date": "2018-01-01",
                    "text": "Healthy patient. No cardiac history.",
                    "hf_gold": 0,
                },
                {
                    "subject_id": 3, "hadm_id": 3, "note_id": "C",
                    "note_date": "2018-01-01",
                    "text": "HFrEF, EF 25%. HF_GOLD_IS_1.",
                    "hf_gold": 1,
                },
                {
                    "subject_id": 4, "hadm_id": 4, "note_id": "D",
                    "note_date": "2018-01-01",
                    "text": "Pneumonia, normal echo.",
                    "hf_gold": 0,
                },
            ],
        )
        config_path = _make_canned_config(
            tmp_path, {"name": "perfect_mock", "model": "perfect-v1"}
        )

        from evaluation.run_demonstration import run

        results_dir = run(
            cohort_path=cohort_path,
            config_path=config_path,
            out_root=out_root,
        )
        metrics = _load_metrics(results_dir)
        assert metrics["n_total"] == 4
        assert metrics["n_processed"] == 4
        assert metrics["n_failed"] == 0
        assert metrics["cohen_kappa"] == 1.0
        assert metrics["accuracy"] == 1.0
        assert metrics["true_positive"] == 2
        assert metrics["true_negative"] == 2
        assert metrics["false_positive"] == 0
        assert metrics["false_negative"] == 0
    finally:
        unregister_provider("perfect_mock")


# ---------------------------------------------------------------------------
# Test 3 — provider failure: half the cohort hits TimeoutError, no crash.
# ---------------------------------------------------------------------------


class _HalfTimeoutProvider(LLMProvider):
    """First half of calls return valid output; second half raise TimeoutError."""

    name = "half_timeout"
    is_external = False
    model = "timeout-v1"

    def __init__(self, **_):
        self._n = 0

    def generate(self, prompt, *, max_tokens=512, temperature=0.0, output_schema=None, timeout_s=60):
        self._n += 1
        # 4-row cohort: rows 1 and 2 succeed, rows 3 and 4 timeout (each attempted
        # once; max_retries=0 means a single attempt per patient).
        if self._n <= 2:
            body = '{"label": 1, "confidence": 0.9, "evidence": "x"}'
            return LLMResponse(
                text=f"<json>{body}</json>",
                finish_reason="stop",
                usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                latency_ms=0,
                cost_usd=0.0,
                raw={},
            )
        raise TimeoutError("synthetic provider timeout")

    def health_check(self):
        return True


def test_handles_provider_failure(tmp_path, out_root):
    from i2b2_cdi.LLM.providers import register_provider, unregister_provider

    register_provider("half_timeout", _HalfTimeoutProvider)
    try:
        cohort_path = _make_canned_cohort(
            tmp_path,
            [
                {"subject_id": i, "hadm_id": i, "note_id": str(i),
                 "note_date": "2018-01-01", "text": "note", "hf_gold": i % 2}
                for i in range(1, 5)
            ],
        )
        config_path = _make_canned_config(
            tmp_path, {"name": "half_timeout", "model": "timeout-v1"}
        )
        from evaluation.run_demonstration import run

        results_dir = run(
            cohort_path=cohort_path,
            config_path=config_path,
            out_root=out_root,
        )
        # Pipeline must NOT have crashed
        assert results_dir.exists()
        metrics = _load_metrics(results_dir)
        assert metrics["n_total"] == 4
        assert metrics["n_processed"] == 2, (
            f"expected exactly 2 succeed before the provider fails; got {metrics['n_processed']}"
        )
        assert metrics["n_failed"] == 2
        # raw_predictions.csv must contain all 4 rows, two with status='failed'
        raw = pd.read_csv(results_dir / "raw_predictions.csv")
        assert len(raw) == 4
        assert (raw["status"] == "failed").sum() == 2
    finally:
        unregister_provider("half_timeout")


# ---------------------------------------------------------------------------
# Test 4 — reproducibility receipt: run_config.json captures git + cohort info.
# ---------------------------------------------------------------------------


def test_run_config_includes_git_hash(out_root):
    from evaluation.run_demonstration import run

    results_dir = run(
        cohort_path=COHORT_CSV,
        config_path=SAMPLE_CONFIG,
        out_root=out_root,
    )
    run_config = json.loads((results_dir / "run_config.json").read_text())
    # git_commit may be None outside a git checkout; on this repo it must
    # be a 40-char sha (or None if `git` is not on PATH).
    git_commit = run_config.get("git_commit")
    assert git_commit is None or (isinstance(git_commit, str) and len(git_commit) == 40), (
        f"expected 40-char git SHA or None; got {git_commit!r}"
    )
    # The other receipt fields are required
    assert "cohort_path" in run_config
    assert "cohort_row_count" in run_config
    assert run_config["cohort_row_count"] == 50
    assert "python" in run_config
    assert "timestamp_utc" in run_config
    assert "config" in run_config
    # The full provider config snapshot should be present
    assert run_config["config"]["provider"]["name"] == "mock"


# ---------------------------------------------------------------------------
# Bonus: per-run audit.sqlite has the right shape.
# ---------------------------------------------------------------------------


def test_audit_sqlite_populated(out_root):
    from evaluation.run_demonstration import run

    results_dir = run(
        cohort_path=COHORT_CSV,
        config_path=SAMPLE_CONFIG,
        out_root=out_root,
    )
    audit_path = results_dir / "audit.sqlite"
    assert audit_path.exists()
    conn = sqlite3.connect(str(audit_path))
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM llm_audit")
    n = cur.fetchone()[0]
    conn.close()
    assert n == 50, f"expected 50 audit rows for the 50-row cohort, got {n}"
