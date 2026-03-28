"""
LLM backend configuration via environment variables.

Configure via:
    LLM_BACKEND=openai|anthropic|gemini
    LLM_BASE_URL=http://10.0.0.17:3001/v1
    LLM_API_KEY=not-needed
    LLM_MODEL=my-local-model

    # Formatter model (for reasoner/formatter pipeline)
    LLM_FORMATTER_BACKEND=openai
    LLM_FORMATTER_BASE_URL=http://10.0.0.17:8002/v1
    LLM_FORMATTER_API_KEY=not-needed
    LLM_FORMATTER_MODEL=my-small-model
"""

import os

BACKEND = os.environ.get("LLM_BACKEND", "openai")
BASE_URL = os.environ.get("LLM_BASE_URL", "http://10.0.0.17:8001/v1")
API_KEY = os.environ.get("LLM_API_KEY", "not-needed")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "unsloth/Qwen3.5-9B-GGUF:Q4_K_M")

# Formatter defaults: separate port for the smaller tool-calling model
FORMATTER_BACKEND = os.environ.get("LLM_FORMATTER_BACKEND", BACKEND)
FORMATTER_BASE_URL = os.environ.get("LLM_FORMATTER_BASE_URL", "http://10.0.0.17:8002/v1")
FORMATTER_API_KEY = os.environ.get("LLM_FORMATTER_API_KEY", API_KEY)
FORMATTER_MODEL = os.environ.get("LLM_FORMATTER_MODEL", DEFAULT_MODEL)


def resolve_model(model, backend):
    """Resolve a model name, falling back to backend-specific defaults."""
    if model:
        return model
    if backend == "openai":
        return DEFAULT_MODEL or "default"
    elif backend == "gemini":
        return "gemini-2.5-flash"
    else:
        return "claude-sonnet-4-20250514"
