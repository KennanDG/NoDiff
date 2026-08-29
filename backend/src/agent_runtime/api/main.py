from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_runtime.api.auth import ApiKeyMiddleware
from agent_runtime.api.routers.health import router as health_router
from agent_runtime.api.routers.coding_agent import router as coding_agent_router
from agent_runtime.api.routers.voice_agent import router as voice_agent_router
from agent_runtime.api.routers.github import router as github_router
from agent_runtime.api.routers.admin import router as admin_router


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
    raw = os.getenv(
        "AGENT_RUNTIME_ALLOWED_ORIGINS",
    )

    if raw:
        origins = [
            item.strip()
            for item in raw.split(",")
            if item.strip()
        ]

        if origins:
            return origins

    # Development fallback.
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def create_app() -> FastAPI:
    app = FastAPI(
        title="AGENT_RUNTIME API",
        version="0.1.0",
    )

    app.add_middleware(
        ApiKeyMiddleware,
    )

    app.add_middleware(
        CORSMiddleware,

        allow_origins=
            _allowed_origins(),


        # The application authenticates with x-api-key rather
        # than cookies, so browser credential mode is not needed.

        allow_credentials=False,

        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(
        health_router,
    )

    app.include_router(
        coding_agent_router,
    )

    app.include_router(
        voice_agent_router,
    )

    app.include_router(
        github_router,
    )

    app.include_router(
        admin_router,
    )


    return app


app = create_app()


def main() -> None:
    host = os.getenv(
        "AGENT_RUNTIME_HOST",
        "127.0.0.1",
    )

    port = int(
        os.getenv(
            "AGENT_RUNTIME_PORT",
            "8765",
        )
    )

    log_level = os.getenv(
        "AGENT_RUNTIME_LOG_LEVEL",
        "info",
    )

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
    )


if __name__ == "__main__":
    main()