from __future__ import annotations

import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
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

logger = logging.getLogger(__name__)


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
    raw = os.getenv("AGENT_RUNTIME_ALLOWED_ORIGINS")

    if raw:
        origins = [item.strip() for item in raw.split(",") if item.strip()]

        if origins:
            return origins

    # Development fallback.
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


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
        # The application authenticates with x-api-key rather than cookies, so
        # browser credential mode is not needed.
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
    host = os.getenv("AGENT_RUNTIME_HOST", "127.0.0.1")
    port = int(os.getenv("AGENT_RUNTIME_PORT", "8765"))
    log_level = os.getenv("AGENT_RUNTIME_LOG_LEVEL", "info")

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=log_level,
    )
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
