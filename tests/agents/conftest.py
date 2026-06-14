"""Shared fixtures for agent integration tests.

Provides:

- ``data_dir``: Path to ``tests/agents/__data__/`` (gitignored artifact output).
- ``load_env``: Loads ``.env`` into ``os.environ`` so ``llm_caller`` picks up
  the backend config (API keys, base URLs, model names).
- ``artifact_path``: Helper that builds an output path inside ``__data__``
  and ensures the parent directory exists.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Data directory — all intermediate artifacts go here
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "__data__"


@pytest.fixture(autouse=True, scope="session")
def load_env():
    """Load .env into os.environ so llm_caller picks up backend config.

    Must run before any module that reads env vars at import time
    (e.g. ``llm_caller.config``).  We use ``session`` scope so it
    executes once, early, before any test module is collected.
    """
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
    # Re-read llm_caller config to pick up env vars that were set after
    # the module was first imported.
    from llm_caller import config as llm_cfg
    llm_cfg.BACKEND = os.environ.get("LLM_BACKEND", llm_cfg.BACKEND)
    llm_cfg.BASE_URL = os.environ.get("LLM_BASE_URL", llm_cfg.BASE_URL)
    llm_cfg.API_KEY = os.environ.get("LLM_API_KEY", llm_cfg.API_KEY)
    llm_cfg.DEFAULT_MODEL = os.environ.get("LLM_MODEL", llm_cfg.DEFAULT_MODEL)
    llm_cfg.LLM_TOOL_CHOICE = os.environ.get("LLM_TOOL_CHOICE", llm_cfg.LLM_TOOL_CHOICE)
    llm_cfg.FORMATTER_BACKEND = os.environ.get("LLM_FORMATTER_BACKEND", llm_cfg.FORMATTER_BACKEND)
    llm_cfg.FORMATTER_BASE_URL = os.environ.get("LLM_FORMATTER_BASE_URL", llm_cfg.FORMATTER_BASE_URL)
    llm_cfg.FORMATTER_API_KEY = os.environ.get("LLM_FORMATTER_API_KEY", llm_cfg.FORMATTER_API_KEY)
    llm_cfg.FORMATTER_MODEL = os.environ.get("LLM_FORMATTER_MODEL", llm_cfg.FORMATTER_MODEL)


@pytest.fixture()
def data_dir(tmp_path_factory) -> Path:
    """Return the ``tests/agents/__data__/`` directory, creating it if needed."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


@pytest.fixture()
def artifact_path(data_dir: Path):
    """Return a function that builds an output path under ``__data__``
    and ensures the parent directory exists.

    Usage::

        def test_foo(artifact_path):
            path = artifact_path("decompose_hlr", "prompt.md")
            # → tests/agents/__data__/decompose_hlr/prompt.md
    """
    def _artifact_path(group: str, filename: str) -> Path:
        dest = data_dir / group / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        return dest
    return _artifact_path