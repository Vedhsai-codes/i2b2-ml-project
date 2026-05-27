# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""Provider registry for the LLM module.

The registry maintains a single source of truth (``PROVIDER_REGISTRY``)
plus two read-optimized views (``LOCAL_PROVIDERS`` and ``EXTERNAL_PROVIDERS``)
that are auto-managed on register/unregister based on the provider's
``is_external`` class attribute.

An import-time assertion (``_assert_registry_invariant``) enforces:
- every entry in ``PROVIDER_REGISTRY`` belongs to exactly one of the two sets
- the two sets are disjoint
- the set membership matches ``cls.is_external``

External providers (text leaves the Docker boundary) require an explicit
opt-in via ``blob['provider']['external_provider'] == true``. See
``get_provider`` for the enforcement.
"""
from __future__ import annotations

from typing import Dict, Set, Type

from loguru import logger

from i2b2_cdi.LLM.providers.base import LLMProvider
from i2b2_cdi.LLM.providers.local_hf import LocalHFProvider
from i2b2_cdi.LLM.providers.ollama import OllamaProvider
from i2b2_cdi.LLM.providers.openai_compatible import OpenAICompatibleProvider
from i2b2_cdi.LLM.providers.anthropic import AnthropicProvider


PROVIDER_REGISTRY: Dict[str, Type[LLMProvider]] = {
    "local_hf": LocalHFProvider,
    "ollama": OllamaProvider,
    "openai_compatible": OpenAICompatibleProvider,
    "anthropic": AnthropicProvider,
}

LOCAL_PROVIDERS: Set[str] = set()
EXTERNAL_PROVIDERS: Set[str] = set()


def _refresh_sets() -> None:
    """Rebuild LOCAL/EXTERNAL view sets from the registry."""
    LOCAL_PROVIDERS.clear()
    EXTERNAL_PROVIDERS.clear()
    for name, cls in PROVIDER_REGISTRY.items():
        if getattr(cls, "is_external", False):
            EXTERNAL_PROVIDERS.add(name)
        else:
            LOCAL_PROVIDERS.add(name)


def _assert_registry_invariant() -> None:
    """Verify LOCAL and EXTERNAL sets agree with the registry. Raises AssertionError."""
    overlap = LOCAL_PROVIDERS & EXTERNAL_PROVIDERS
    if overlap:
        raise AssertionError(
            f"LLM provider registry inconsistent: {overlap} appear in both LOCAL and EXTERNAL"
        )
    for name, cls in PROVIDER_REGISTRY.items():
        expected_external = bool(getattr(cls, "is_external", False))
        in_external = name in EXTERNAL_PROVIDERS
        in_local = name in LOCAL_PROVIDERS
        if expected_external and not in_external:
            raise AssertionError(
                f"Provider {name!r} is external (is_external=True) but not in EXTERNAL_PROVIDERS"
            )
        if not expected_external and not in_local:
            raise AssertionError(
                f"Provider {name!r} is local (is_external=False) but not in LOCAL_PROVIDERS"
            )
        if expected_external and in_local:
            raise AssertionError(
                f"Provider {name!r} marked external but also in LOCAL_PROVIDERS"
            )
        if not expected_external and in_external:
            raise AssertionError(
                f"Provider {name!r} marked local but also in EXTERNAL_PROVIDERS"
            )
    for name in LOCAL_PROVIDERS | EXTERNAL_PROVIDERS:
        if name not in PROVIDER_REGISTRY:
            raise AssertionError(
                f"Provider {name!r} appears in LOCAL/EXTERNAL but not in PROVIDER_REGISTRY"
            )


def register_provider(name: str, cls: Type[LLMProvider]) -> None:
    """Register a provider class. Auto-updates LOCAL/EXTERNAL view sets.

    Args:
        name: Registry key (used in concept_blob['provider']['name']).
        cls: A concrete subclass of LLMProvider.

    Raises:
        TypeError: if cls is not a subclass of LLMProvider.
        AssertionError: if the resulting registry state violates the invariant.
    """
    if not isinstance(cls, type) or not issubclass(cls, LLMProvider):
        raise TypeError(f"register_provider expects an LLMProvider subclass, got {cls!r}")
    PROVIDER_REGISTRY[name] = cls
    _refresh_sets()
    _assert_registry_invariant()
    logger.debug("Registered LLM provider {!r} (external={})", name, getattr(cls, "is_external", False))


def unregister_provider(name: str) -> None:
    """Remove a provider from the registry. Idempotent for unknown names."""
    PROVIDER_REGISTRY.pop(name, None)
    _refresh_sets()
    _assert_registry_invariant()


def get_provider(provider_config: dict) -> LLMProvider:
    """Construct a provider from a concept_blob['provider'] dict.

    Args:
        provider_config: dict with keys ``name``, ``model``, and optional
            ``external_provider``. Provider-specific options are forwarded.

    Raises:
        KeyError: unknown provider name.
        PermissionError: provider is_external but external_provider opt-in not set.
    """
    if not isinstance(provider_config, dict):
        raise TypeError(f"provider config must be a dict, got {type(provider_config).__name__}")
    name = provider_config.get("name")
    if not name:
        raise KeyError("provider config missing required 'name' field")
    if name not in PROVIDER_REGISTRY:
        raise KeyError(
            f"Unknown LLM provider {name!r}. Registered: {sorted(PROVIDER_REGISTRY.keys())}"
        )
    cls = PROVIDER_REGISTRY[name]
    is_external = bool(getattr(cls, "is_external", False))
    opt_in = bool(provider_config.get("external_provider", False))
    if is_external and not opt_in:
        raise PermissionError(
            f"Provider {name!r} is external (text leaves Docker boundary). "
            f"Set blob['provider']['external_provider']=true to opt in."
        )
    kwargs = {k: v for k, v in provider_config.items() if k not in ("name", "external_provider")}
    return cls(**kwargs)


_refresh_sets()
_assert_registry_invariant()


__all__ = [
    "PROVIDER_REGISTRY",
    "LOCAL_PROVIDERS",
    "EXTERNAL_PROVIDERS",
    "register_provider",
    "unregister_provider",
    "get_provider",
]
