from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)


def disable_langsmith_tracing() -> None:
    """Disable LangSmith/LangChain tracing for the entire FastAPI sidecar.

    This function is intentionally called before importing any module that builds
    LangChain/LangGraph runtimes. Assign values unconditionally so a parent Electron
    environment, .env file, or launching shell cannot accidentally re-enable tracing
    for this diagnostic configuration.
    """

    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGCHAIN_TRACING"] = "false"
    os.environ["LANGCHAIN_CALLBACKS_BACKGROUND"] = "false"

    logger.info("LangSmith tracing is disabled for this FastAPI process")


# Backward-compatible alias for code that still imports the previous bootstrap API.
# It now disables tracing instead of configuring a LangSmith client.
def ensure_langsmith_env() -> None:
    disable_langsmith_tracing()


def langsmith_tracing_enabled() -> bool:
    return False


@contextmanager
def langsmith_trace_scope(
    *,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Iterator[None]:
    """Compatibility no-op. No LangSmith client or tracer is created."""

    del tags, metadata
    yield


def close_langsmith_client(timeout_seconds: float = 0.0) -> None:
    """Compatibility no-op; this diagnostic build never creates a LangSmith client."""

    del timeout_seconds
