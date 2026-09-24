from __future__ import annotations

import logging
import os
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from typing import AsyncIterator

import uvicorn
from agent_runtime.config.langsmith_bootstrap import disable_langsmith_tracing

# IMPORTANT: disable tracing before importing any router/module that may construct
# LangChain/LangGraph runtimes. This overrides values inherited from Electron,
# the shell, or .env for this diagnostic build.
disable_langsmith_tracing()

from agent_runtime.agents.coding.memory import initialize_coding_agent_memory
from agent_runtime.api.auth import ApiKeyMiddleware
from agent_runtime.api.routers.admin import router as admin_router
from agent_runtime.api.routers.coding_agent import router as coding_agent_router
from agent_runtime.api.routers.github import router as github_router
from agent_runtime.api.routers.health import router as health_router
from agent_runtime.api.routers.voice_agent import router as voice_agent_router
from agent_runtime.config.settings import settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _configure_runtime_logging() -> RotatingFileHandler:
    log_directory = settings.agent_runtime_data_dir / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)
    log_path = log_directory / "runtime.log"
    handler = RotatingFileHandler(log_path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(process)d] %(message)s"
    ))
    for name in ("", "uvicorn"):
        target = logging.getLogger(name)
        target.setLevel(logging.INFO)
        target.addHandler(handler)
    logger.info("Runtime logging started: %s", log_path)
    return handler


async def _request_diagnostics(request, call_next):
    request_id = uuid.uuid4().hex[:10]
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Request %s failed: %s %s", request_id, request.method, request.url.path)
        response = JSONResponse(
            status_code=500,
            content={"detail": f"Internal error (request {request_id}). See logs/runtime.log in NoDiff agent-runtime."},
        )
    elapsed = (time.monotonic() - started) * 1000
    if response.status_code >= 400 or elapsed >= 10_000:
        logger.warning("Request %s %s %s -> %s (%.0fms)", request_id, request.method,
                       request.url.path, response.status_code, elapsed)
    response.headers["X-Request-ID"] = request_id
    return response


def _env_bool(
    name: str,
    default: bool = False,
) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _allowed_origins() -> list[str]:
    """Return explicit renderer origins allowed to call the loopback sidecar.

    Electron development may move Vite to another free port, while packaged
    file:// renderers use the serialized Origin value ``null``. Exact configured
    origins are preserved here; localhost/loopback any-port support is provided
    by ``_LOCAL_RENDERER_ORIGIN_REGEX`` below.
    """
    raw = os.getenv("AGENT_RUNTIME_ALLOWED_ORIGINS")
    origins = [item.strip() for item in raw.split(",") if item.strip()] if raw else []

    # Keep deterministic fallbacks for standalone backend development and the
    # packaged file:// renderer.
    for origin in (
        "null",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ):
        if origin not in origins:
            origins.append(origin)

    return origins


_LOCAL_RENDERER_ORIGIN_REGEX = (
    r"^(?:null|https?://(?:localhost|127\.0\.0\.1)(?::\d+)?)$"
)


async def _private_network_access_middleware(request, call_next):
    """Allow Chromium/Electron local-network preflights to reach FastAPI.

    New Chromium builds can issue an OPTIONS request containing
    ``Access-Control-Request-Private-Network: true`` before a renderer calls a
    loopback service. A normal 200 OPTIONS response is still rejected by the
    browser unless the response explicitly opts into private-network access.
    """
    response = await call_next(request)

    if (
        request.method == "OPTIONS"
        and request.headers.get("access-control-request-private-network", "").lower()
        == "true"
    ):
        response.headers["Access-Control-Allow-Private-Network"] = "true"

    return response


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    if settings.agent_runtime_initialize_memory_on_startup:
        try:
            initialize_coding_agent_memory()
        except Exception:
            logger.exception("Coding-agent memory initialization failed")
            if settings.agent_runtime_memory_init_strict:
                raise

    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AGENT_RUNTIME API",
        version="0.1.0",
        lifespan=_lifespan,
    )

    app.add_middleware(ApiKeyMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_origin_regex=_LOCAL_RENDERER_ORIGIN_REGEX,
        # The application authenticates with x-api-key rather than cookies, so
        # browser credential mode is not needed.
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register this after CORSMiddleware so it wraps the CORS preflight response
    # and can add Chromium's private-network opt-in header when requested.
    app.middleware("http")(_private_network_access_middleware)
    app.middleware("http")(_request_diagnostics)

    app.include_router(health_router)
    app.include_router(coding_agent_router)
    app.include_router(voice_agent_router)
    app.include_router(github_router)
    app.include_router(admin_router)

    return app


app = create_app()


def _monitor_parent_stdin(server: uvicorn.Server) -> None:
    """Request a graceful Uvicorn shutdown when the Electron parent asks for it.

    Electron launches the packaged FastAPI runtime with stdin connected to a pipe.
    Sending ``shutdown\n`` lets Uvicorn complete its normal lifespan shutdown before
    the desktop process exits. EOF is treated the same way, which also prevents an
    orphaned sidecar if the parent process disappears unexpectedly.
    """

    stream = sys.stdin
    if stream is None:
        return

    try:
        for line in stream:
            if line.strip().lower() == "shutdown":
                logger.info("Desktop parent requested FastAPI shutdown")
                server.should_exit = True
                return

        # Parent closed the pipe without sending the sentinel.
        server.should_exit = True
    except Exception:
        logger.exception("Failed while monitoring the desktop shutdown pipe")


def main() -> None:
    file_handler = _configure_runtime_logging()
    host = os.getenv("AGENT_RUNTIME_HOST", "127.0.0.1")
    port = int(os.getenv("AGENT_RUNTIME_PORT", "8765"))
    log_level = os.getenv("AGENT_RUNTIME_LOG_LEVEL", "info")

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=log_level,
    )
    # Uvicorn installs its own logger configuration when Config is constructed.
    # Reattach the persistent handler after that setup.
    uvicorn_logger = logging.getLogger("uvicorn")
    if file_handler not in uvicorn_logger.handlers:
        uvicorn_logger.addHandler(file_handler)
    server = uvicorn.Server(config)

    shutdown_monitor = threading.Thread(
        target=_monitor_parent_stdin,
        args=(server,),
        name="desktop-shutdown-monitor",
        daemon=True,
    )
    shutdown_monitor.start()
    server.run()


if __name__ == "__main__":
    main()
