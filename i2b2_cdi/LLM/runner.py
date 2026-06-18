# Copyright 2025 Massachusetts General Hospital.
# Apache-2.0
"""CLI subcommand entry-point for the LLM module.

The ``i2b2_cdi/__main__.py`` orchestrator auto-discovers each subdirectory's
``runner.py`` via ``glob.glob('i2b2_cdi/*/runner.py')`` and calls its
``mod_run(options)``. Stub-only for now; richer subcommands (smoke test,
prompt render preview, audit dump) can be added without touching __main__.
"""
from __future__ import annotations

from loguru import logger


def mod_run(options):
    """No-op for now. Reserved for ``etl llm <subcommand>`` in future sprints."""
    cmd = getattr(options, "command", None) or getattr(options, "subcommand", None)
    if cmd:
        logger.debug("i2b2_cdi.LLM.runner: command={} (no action wired yet)", cmd)
    return None
