"""Run with: uv run python scripts/diagnose_memory.py [--sqlite-only]."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import replace
from importlib.metadata import PackageNotFoundError, version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite-only", action="store_true",
        help="Check SQLite setup without downloading/loading the embedding model.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    print(f"Python executable: {sys.executable}", flush=True)
    print(f"Python base prefix: {sys.base_prefix}", flush=True)
    print(f"APPDATA: {os.getenv('APPDATA', '(unset)')}", flush=True)
    for name in ("fastembed", "huggingface-hub", "langchain-community", "langgraph-checkpoint-sqlite"):
        try:
            print(f"{name}: {version(name)}", flush=True)
        except PackageNotFoundError:
            print(f"{name}: NOT INSTALLED", flush=True)

    try:
        from agent_runtime.config.settings import RUNTIME_ENV_FILE, settings as runtime
        from agent_runtime.agents.coding.coding_agent_settings import settings
        from agent_runtime.agents.coding.memory import initialize_coding_agent_memory

        print(f"Dotenv file: {RUNTIME_ENV_FILE}", flush=True)
        print(f"Runtime root: {runtime.agent_runtime_data_dir}", flush=True)
        print(f"Checkpoint database: {settings.memory_checkpoint_db_path}", flush=True)
        print(f"Memory store: {settings.memory_store_db_path}", flush=True)
        print(f"Embedding cache: {settings.memory_embedding_cache_dir}", flush=True)
        print(f"Semantic memory configured: {settings.memory_semantic_enabled}", flush=True)
        # Diagnose initialization without pruning any existing user memories.
        cfg = replace(
            settings,
            memory_semantic_enabled=False if args.sqlite_only else settings.memory_semantic_enabled,
            memory_maintenance_enabled=False,
            memory_vacuum_enabled=False,
        )
        if not initialize_coding_agent_memory(cfg):
            print("Memory is disabled by configuration; no initialization was performed.")
            return 1
    except Exception:
        logging.exception("Memory initialization check failed")
        return 1

    if args.sqlite_only or not cfg.memory_semantic_enabled:
        print("SQLite initialization succeeded. Embedding model was not checked.")
    else:
        print("SQLite and local embedding-model initialization succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
