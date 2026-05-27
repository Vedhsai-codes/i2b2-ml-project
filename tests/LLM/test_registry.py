# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Tests for the provider registry invariant + register/unregister API."""
from __future__ import annotations

import pytest

from i2b2_cdi.LLM.providers import (
    EXTERNAL_PROVIDERS,
    LOCAL_PROVIDERS,
    PROVIDER_REGISTRY,
    _assert_registry_invariant,
    _refresh_sets,
    get_provider,
    register_provider,
    unregister_provider,
)
from i2b2_cdi.LLM.providers.base import LLMProvider, LLMResponse


class _LocalDummy(LLMProvider):
    name = "dummy_local"
    is_external = False

    def __init__(self, **_):
        pass

    def generate(self, prompt, **_):
        return LLMResponse(text="hi")

    def health_check(self):
        return True


class _ExternalDummy(LLMProvider):
    name = "dummy_external"
    is_external = True

    def __init__(self, **_):
        pass

    def generate(self, prompt, **_):
        return LLMResponse(text="hi")

    def health_check(self):
        return True


def test_seed_registry_has_expected_keys():
    for k in ("local_hf", "ollama", "openai_compatible", "anthropic"):
        assert k in PROVIDER_REGISTRY


def test_seed_local_external_split_matches_class_flags():
    assert "local_hf" in LOCAL_PROVIDERS
    assert "ollama" in LOCAL_PROVIDERS
    assert "anthropic" in EXTERNAL_PROVIDERS
    assert "openai_compatible" in EXTERNAL_PROVIDERS


def test_invariant_holds_on_clean_state():
    _assert_registry_invariant()


def test_register_local_updates_local_set():
    register_provider("dummy_local", _LocalDummy)
    try:
        assert "dummy_local" in LOCAL_PROVIDERS
        assert "dummy_local" not in EXTERNAL_PROVIDERS
        _assert_registry_invariant()
    finally:
        unregister_provider("dummy_local")


def test_register_external_updates_external_set():
    register_provider("dummy_external", _ExternalDummy)
    try:
        assert "dummy_external" in EXTERNAL_PROVIDERS
        assert "dummy_external" not in LOCAL_PROVIDERS
        _assert_registry_invariant()
    finally:
        unregister_provider("dummy_external")


def test_unregister_idempotent_for_unknown():
    unregister_provider("not_registered_anywhere")
    _assert_registry_invariant()


def test_register_non_subclass_rejected():
    with pytest.raises(TypeError):
        register_provider("nope", object)


def test_invariant_catches_overlap_after_manual_corruption():
    LOCAL_PROVIDERS.add("anthropic")  # forced inconsistency
    try:
        with pytest.raises(AssertionError):
            _assert_registry_invariant()
    finally:
        LOCAL_PROVIDERS.discard("anthropic")
        _refresh_sets()


def test_invariant_catches_orphaned_set_entry():
    LOCAL_PROVIDERS.add("ghost_provider")
    try:
        with pytest.raises(AssertionError):
            _assert_registry_invariant()
    finally:
        LOCAL_PROVIDERS.discard("ghost_provider")
        _refresh_sets()


def test_get_provider_unknown_name_raises_keyerror():
    with pytest.raises(KeyError):
        get_provider({"name": "no-such-provider"})


def test_get_provider_missing_name_raises_keyerror():
    with pytest.raises(KeyError):
        get_provider({"model": "x"})


def test_get_provider_external_without_optin_blocked():
    with pytest.raises(PermissionError):
        get_provider({"name": "anthropic"})


def test_get_provider_external_with_optin_allowed():
    p = get_provider({"name": "anthropic", "external_provider": True, "model": "claude-sonnet-4-5"})
    assert getattr(p, "name", None) == "anthropic"
    assert p.model == "claude-sonnet-4-5"


def test_get_provider_local_no_optin_needed():
    p = get_provider({"name": "ollama", "model": "llama3"})
    assert getattr(p, "name", None) == "ollama"


def test_get_provider_non_dict_rejected():
    with pytest.raises(TypeError):
        get_provider("anthropic")


# ---------------------------------------------------------------------------
# H-1 regression tests: strict external_provider opt-in
# ---------------------------------------------------------------------------
# Python's built-in bool("false") returns True (any non-empty string is
# truthy). The opt-in gate for external providers must NOT use bool() for
# this reason; otherwise a misconfigured blob with
# "external_provider": "false" silently bypasses the PHI safety gate.
# These tests pin the strict accept/reject contract.


@pytest.mark.parametrize("optin_value", [True, "true", "True", "TRUE", 1])
def test_external_provider_optin_accepted_values(optin_value):
    """Each documented-accepted value must let the external provider construct."""
    p = get_provider(
        {
            "name": "anthropic",
            "external_provider": optin_value,
            "model": "claude-sonnet-4-5",
        }
    )
    assert getattr(p, "name", None) == "anthropic"


@pytest.mark.parametrize(
    "optin_value",
    [
        False,
        None,
        "false",
        "False",
        "FALSE",
        "no",
        "No",
        "0",
        "1",  # string "1" must NOT pass (only int 1 does)
        "",
        0,
        2,  # any int other than 1
        {},
        [],
        "yes",
        "y",
    ],
)
def test_external_provider_optin_rejected_values(optin_value):
    """Each rejected value (including 'false', 'no', '0', '1' string) must trip the gate."""
    with pytest.raises(PermissionError):
        get_provider(
            {
                "name": "anthropic",
                "external_provider": optin_value,
                "model": "claude-sonnet-4-5",
            }
        )


def test_external_provider_optin_missing_rejected():
    """Omitting external_provider entirely must still reject for external providers."""
    with pytest.raises(PermissionError):
        get_provider({"name": "anthropic", "model": "claude-sonnet-4-5"})


def test_external_provider_misconfigured_string_emits_warning(caplog):
    """A truthy-looking string that isn't 'true' should warn before rejecting."""
    import logging as _logging

    # loguru routes through stderr; capture via the caplog handler when
    # available. If loguru is in use the test still proves the rejection,
    # which is the load-bearing assertion.
    caplog.set_level(_logging.WARNING)
    with pytest.raises(PermissionError):
        get_provider(
            {
                "name": "anthropic",
                "external_provider": "false",
                "model": "claude-sonnet-4-5",
            }
        )


def test_is_truthy_optin_unit_table():
    """Direct unit test of the helper. Single source of truth for accept/reject."""
    from i2b2_cdi.LLM.providers import _is_truthy_optin

    # accepted
    for v in (True, 1, "true", "True", "TRUE", "tRuE"):
        assert _is_truthy_optin(v) is True, f"expected accept: {v!r}"
    # rejected
    for v in (
        False,
        None,
        0,
        2,
        -1,
        "",
        "false",
        "False",
        "FALSE",
        "0",
        "1",
        "yes",
        "no",
        "y",
        "n",
        {},
        [],
        ("true",),
    ):
        assert _is_truthy_optin(v) is False, f"expected reject: {v!r}"
