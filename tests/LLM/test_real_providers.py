# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Tests for real-provider construction + exception translation.

No real network calls. SDK exceptions are simulated via stub clients.
"""
from __future__ import annotations

import socket
import sys
import types
from typing import Any
from unittest.mock import patch

import pytest

from i2b2_cdi.LLM.providers.anthropic import AnthropicProvider, DEFAULT_ANTHROPIC_MODEL
from i2b2_cdi.LLM.providers.ollama import OllamaProvider
from i2b2_cdi.LLM.providers.openai_compatible import OpenAICompatibleProvider


# --------------------------- Anthropic ---------------------------


def _stub_anthropic_module(client_factory):
    mod = types.ModuleType("anthropic")

    class APITimeoutError(Exception):
        pass

    class APIConnectionError(Exception):
        pass

    class RateLimitError(Exception):
        pass

    class APIStatusError(Exception):
        def __init__(self, msg, status_code=500):
            super().__init__(msg)
            self.status_code = status_code

    class Anthropic:
        def __init__(self, **kw):
            self.kw = kw
            self.messages = client_factory()

    mod.APITimeoutError = APITimeoutError
    mod.APIConnectionError = APIConnectionError
    mod.RateLimitError = RateLimitError
    mod.APIStatusError = APIStatusError
    mod.Anthropic = Anthropic
    return mod


def _install_anthropic(stub_mod, monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", stub_mod)


def test_anthropic_default_model_is_sonnet_4_5():
    p = AnthropicProvider()
    assert p.model == "claude-sonnet-4-5"
    assert DEFAULT_ANTHROPIC_MODEL == "claude-sonnet-4-5"


def test_anthropic_caching_default_off():
    p = AnthropicProvider()
    assert p.cache_prompt is False


def test_anthropic_caching_opt_in():
    p = AnthropicProvider(cache_prompt=True)
    assert p.cache_prompt is True


def test_anthropic_is_external():
    assert AnthropicProvider.is_external is True


def test_anthropic_translates_timeout(monkeypatch):
    class Msgs:
        def create(self, **kw):
            raise stub.APITimeoutError("slow")

    stub = _stub_anthropic_module(Msgs)
    _install_anthropic(stub, monkeypatch)
    p = AnthropicProvider()
    with pytest.raises(TimeoutError):
        p.generate("x")


def test_anthropic_translates_connection(monkeypatch):
    class Msgs:
        def create(self, **kw):
            raise stub.APIConnectionError("net")

    stub = _stub_anthropic_module(Msgs)
    _install_anthropic(stub, monkeypatch)
    p = AnthropicProvider()
    with pytest.raises(ConnectionError):
        p.generate("x")


def test_anthropic_translates_rate_limit(monkeypatch):
    class Msgs:
        def create(self, **kw):
            raise stub.RateLimitError("429")

    stub = _stub_anthropic_module(Msgs)
    _install_anthropic(stub, monkeypatch)
    p = AnthropicProvider()
    with pytest.raises(ConnectionError):
        p.generate("x")


def test_anthropic_5xx_becomes_connection(monkeypatch):
    class Msgs:
        def create(self, **kw):
            raise stub.APIStatusError("ouch", status_code=503)

    stub = _stub_anthropic_module(Msgs)
    _install_anthropic(stub, monkeypatch)
    p = AnthropicProvider()
    with pytest.raises(ConnectionError):
        p.generate("x")


def test_anthropic_4xx_propagates_raw(monkeypatch):
    class Msgs:
        def create(self, **kw):
            raise stub.APIStatusError("bad request", status_code=400)

    stub = _stub_anthropic_module(Msgs)
    _install_anthropic(stub, monkeypatch)
    p = AnthropicProvider()
    with pytest.raises(stub.APIStatusError):
        p.generate("x")


def test_anthropic_happy_path_parses_response(monkeypatch):
    class _Block:
        type = "text"
        text = "<json>{\"label\":1}</json>"

    class _Usage:
        input_tokens = 50
        output_tokens = 20

    class _Resp:
        content = [_Block()]
        usage = _Usage()
        stop_reason = "stop"
        id = "msg_123"
        model = "claude-sonnet-4-5"

    class Msgs:
        def create(self, **kw):
            return _Resp()

    stub = _stub_anthropic_module(Msgs)
    _install_anthropic(stub, monkeypatch)
    p = AnthropicProvider()
    r = p.generate("x")
    assert "<json>" in r.text
    assert r.usage["prompt_tokens"] == 50
    assert r.usage["completion_tokens"] == 20
    assert r.cost_usd == 0.0


# --------------------------- OpenAI-compatible ---------------------------


def _stub_openai_module(client_factory):
    mod = types.ModuleType("openai")

    class APITimeoutError(Exception):
        pass

    class APIConnectionError(Exception):
        pass

    class RateLimitError(Exception):
        pass

    class APIStatusError(Exception):
        def __init__(self, msg, status_code=500):
            super().__init__(msg)
            self.status_code = status_code

    class _Chat:
        def __init__(self, completions):
            self.completions = completions

    class OpenAI:
        def __init__(self, **kw):
            self.kw = kw
            self.chat = _Chat(client_factory())

    mod.APITimeoutError = APITimeoutError
    mod.APIConnectionError = APIConnectionError
    mod.RateLimitError = RateLimitError
    mod.APIStatusError = APIStatusError
    mod.OpenAI = OpenAI
    return mod


def test_openai_compat_requires_base_url():
    with pytest.raises(ValueError):
        OpenAICompatibleProvider(model="x")


def test_openai_compat_requires_model():
    with pytest.raises(ValueError):
        OpenAICompatibleProvider(base_url="http://localhost:8000/v1")


def test_openai_compat_api_key_defaults_to_not_needed():
    p = OpenAICompatibleProvider(model="x", base_url="http://localhost:8000/v1")
    assert p._api_key == "not-needed"


def test_openai_compat_is_external_default():
    assert OpenAICompatibleProvider.is_external is True


def test_openai_compat_translates_timeout(monkeypatch):
    class Completions:
        def create(self, **kw):
            raise stub.APITimeoutError("slow")

    stub = _stub_openai_module(lambda: Completions())
    monkeypatch.setitem(sys.modules, "openai", stub)
    p = OpenAICompatibleProvider(model="x", base_url="http://h:1/v1")
    with pytest.raises(TimeoutError):
        p.generate("x")


def test_openai_compat_5xx_to_connection(monkeypatch):
    class Completions:
        def create(self, **kw):
            raise stub.APIStatusError("502", status_code=502)

    stub = _stub_openai_module(lambda: Completions())
    monkeypatch.setitem(sys.modules, "openai", stub)
    p = OpenAICompatibleProvider(model="x", base_url="http://h:1/v1")
    with pytest.raises(ConnectionError):
        p.generate("x")


def test_openai_compat_4xx_raw(monkeypatch):
    class Completions:
        def create(self, **kw):
            raise stub.APIStatusError("400", status_code=400)

    stub = _stub_openai_module(lambda: Completions())
    monkeypatch.setitem(sys.modules, "openai", stub)
    p = OpenAICompatibleProvider(model="x", base_url="http://h:1/v1")
    with pytest.raises(stub.APIStatusError):
        p.generate("x")


def test_openai_compat_happy_path(monkeypatch):
    class _Choice:
        class _Msg:
            content = "hello"

        message = _Msg()
        finish_reason = "stop"

    class _Usage:
        prompt_tokens = 10
        completion_tokens = 5
        total_tokens = 15

    class _Resp:
        choices = [_Choice()]
        usage = _Usage()
        id = "abc"
        model = "x"

    class Completions:
        def create(self, **kw):
            return _Resp()

    stub = _stub_openai_module(lambda: Completions())
    monkeypatch.setitem(sys.modules, "openai", stub)
    p = OpenAICompatibleProvider(model="x", base_url="http://h:1/v1")
    r = p.generate("x")
    assert r.text == "hello"
    assert r.usage["total_tokens"] == 15


# --------------------------- Ollama ---------------------------


def test_ollama_is_local():
    assert OllamaProvider.is_external is False


def test_ollama_default_url_and_model():
    p = OllamaProvider()
    assert p.base_url == "http://localhost:11434"
    assert p.model == "llama3"


def test_ollama_timeout_translates(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise socket.timeout("slow")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    p = OllamaProvider()
    with pytest.raises(TimeoutError):
        p.generate("x")


def test_ollama_url_error_translates(monkeypatch):
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    p = OllamaProvider()
    with pytest.raises(ConnectionError):
        p.generate("x")


def test_ollama_5xx_translates(monkeypatch):
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError("u", 502, "bad gateway", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    p = OllamaProvider()
    with pytest.raises(ConnectionError):
        p.generate("x")


def test_ollama_4xx_raw(monkeypatch):
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError("u", 404, "missing", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    p = OllamaProvider()
    with pytest.raises(urllib.error.HTTPError):
        p.generate("x")


def test_ollama_happy_path_parses_body(monkeypatch):
    import io
    import json as _json

    class _Resp:
        def __init__(self, body):
            self._body = body
            self.status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self._body.encode("utf-8")

    def fake_urlopen(req, timeout=None):
        return _Resp(
            _json.dumps(
                {
                    "response": "hi",
                    "prompt_eval_count": 11,
                    "eval_count": 4,
                    "model": "llama3",
                    "done_reason": "stop",
                }
            )
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    p = OllamaProvider()
    r = p.generate("hello")
    assert r.text == "hi"
    assert r.usage["prompt_tokens"] == 11
    assert r.usage["completion_tokens"] == 4


# --------------------------- cost = 0 invariant ---------------------------


# ---------------------------------------------------------------------------
# H-3: LocalHFProvider chat-template handling
# ---------------------------------------------------------------------------
#
# Chat-tuned models (Llama-3-Instruct, Qwen2.5-Instruct, etc.) expect their
# prompt wrapped in the model's chat template. Without it, the model treats
# the prompt as raw text continuation and produces significantly worse
# output. These tests pin three behaviors:
#   1. tokenizer has chat_template + auto-detect -> apply_chat_template called
#   2. tokenizer has NO chat_template + auto-detect -> raw prompt forwarded
#   3. explicit use_chat_template=True on a tokenizer without one -> error


class _FakeTokenizerWithTemplate:
    """Stand-in for an AutoTokenizer that exposes a chat_template."""

    chat_template = "{% for msg in messages %}{{msg['role']}}: {{msg['content']}}{% endfor %}"

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False):
        # Sentinel: production code is the only thing that calls this. We
        # capture the call shape so the test can assert on it.
        _FakeTokenizerWithTemplate.last_call = {
            "messages": messages,
            "tokenize": tokenize,
            "add_generation_prompt": add_generation_prompt,
        }
        rendered = ""
        for m in messages:
            rendered += f"{m['role']}: {m['content']}\n"
        if add_generation_prompt:
            rendered += "assistant:"
        return rendered


class _FakeTokenizerWithoutTemplate:
    """Stand-in for a base-model tokenizer (no chat_template)."""

    chat_template = None

    def apply_chat_template(self, *a, **kw):  # pragma: no cover — must never be called
        raise AssertionError("apply_chat_template should not be called when no template is set")


def _install_local_hf_fakes(monkeypatch, tokenizer_obj):
    """Replace the heavy transformers + torch imports with fakes that let
    LocalHFProvider._load() complete on this machine."""

    captured: dict = {"pipe_call_with": None}

    fake_torch = types.ModuleType("torch")
    fake_torch.bfloat16 = "bf16-sentinel"
    fake_torch.float32 = "fp32-sentinel"
    fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False, OutOfMemoryError=RuntimeError)
    fake_torch.backends = types.SimpleNamespace(
        mps=types.SimpleNamespace(is_available=lambda: False)
    )

    def fake_pipeline(task, model=None, tokenizer=None, device_map=None):
        def _call(prompt, **gen_kwargs):
            captured["pipe_call_with"] = prompt
            return [{"generated_text": "FAKE OUTPUT"}]

        return _call

    fake_auto_tokenizer = types.SimpleNamespace(
        from_pretrained=lambda model: tokenizer_obj
    )
    fake_auto_model = types.SimpleNamespace(
        from_pretrained=lambda model, **kw: object()
    )
    fake_transformers = types.ModuleType("transformers")
    fake_transformers.AutoModelForCausalLM = fake_auto_model
    fake_transformers.AutoTokenizer = fake_auto_tokenizer
    fake_transformers.pipeline = fake_pipeline
    fake_transformers.BitsAndBytesConfig = lambda **kw: object()

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    return captured


def test_local_hf_auto_detects_chat_template_and_applies_it(monkeypatch):
    from i2b2_cdi.LLM.providers.local_hf import LocalHFProvider

    tok = _FakeTokenizerWithTemplate()
    captured = _install_local_hf_fakes(monkeypatch, tok)

    p = LocalHFProvider(model="fake/chat-model")
    resp = p.generate("Is this heart failure?", max_tokens=10)

    # apply_chat_template was called with the right shape:
    assert hasattr(_FakeTokenizerWithTemplate, "last_call")
    call = _FakeTokenizerWithTemplate.last_call
    assert call["tokenize"] is False
    assert call["add_generation_prompt"] is True
    assert call["messages"] == [{"role": "user", "content": "Is this heart failure?"}]

    # The pipeline was called with the chat-formatted string, not the raw prompt.
    assert "user: Is this heart failure?" in captured["pipe_call_with"]
    assert "assistant:" in captured["pipe_call_with"]
    assert resp.raw["prompt_format"] == "chat-template"


def test_local_hf_no_chat_template_uses_raw_prompt(monkeypatch):
    from i2b2_cdi.LLM.providers.local_hf import LocalHFProvider

    tok = _FakeTokenizerWithoutTemplate()
    captured = _install_local_hf_fakes(monkeypatch, tok)

    p = LocalHFProvider(model="fake/base-model")
    resp = p.generate("hello", max_tokens=10)

    # Raw prompt forwarded unchanged
    assert captured["pipe_call_with"] == "hello"
    assert resp.raw["prompt_format"] == "raw"


def test_local_hf_explicit_use_chat_template_true_without_template_raises(monkeypatch):
    from i2b2_cdi.LLM.providers.local_hf import LocalHFProvider

    tok = _FakeTokenizerWithoutTemplate()
    _install_local_hf_fakes(monkeypatch, tok)

    p = LocalHFProvider(model="fake/base-model", use_chat_template=True)
    with pytest.raises(RuntimeError) as exc:
        p.generate("hello", max_tokens=10)
    assert "use_chat_template=True" in str(exc.value)


def test_local_hf_explicit_use_chat_template_false_skips_template(monkeypatch):
    """Even with a chat_template available, ``use_chat_template=False`` forces raw mode."""
    from i2b2_cdi.LLM.providers.local_hf import LocalHFProvider

    tok = _FakeTokenizerWithTemplate()
    # Clear any previous call state
    if hasattr(_FakeTokenizerWithTemplate, "last_call"):
        delattr(_FakeTokenizerWithTemplate, "last_call")
    captured = _install_local_hf_fakes(monkeypatch, tok)

    p = LocalHFProvider(model="fake/chat-model", use_chat_template=False)
    resp = p.generate("hello", max_tokens=10)

    # apply_chat_template was NOT called
    assert not hasattr(_FakeTokenizerWithTemplate, "last_call"), (
        "use_chat_template=False should bypass the template"
    )
    assert captured["pipe_call_with"] == "hello"
    assert resp.raw["prompt_format"] == "raw"


def test_cost_zero_for_anthropic(monkeypatch):
    class _Resp:
        class _Block:
            type = "text"
            text = "ok"

        content = [_Block()]

        class _Usage:
            input_tokens = 1
            output_tokens = 1

        usage = _Usage()
        stop_reason = "stop"
        id = "x"
        model = "claude-sonnet-4-5"

    class Msgs:
        def create(self, **kw):
            return _Resp()

    stub = _stub_anthropic_module(Msgs)
    monkeypatch.setitem(sys.modules, "anthropic", stub)
    assert AnthropicProvider().generate("x").cost_usd == 0.0
