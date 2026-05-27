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
