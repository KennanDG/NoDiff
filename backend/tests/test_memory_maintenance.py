from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from agent_runtime.agents.coding.coding_agent_settings import settings
from agent_runtime.agents.coding.memory import (
    _compact_sqlite_file,
    _ensure_checkpoint_schema,
    _maintenance_is_due,
    _prune_checkpoint_history,
    initialize_coding_agent_memory,
)
from langgraph.checkpoint.sqlite import SqliteSaver


def test_checkpoint_schema_uses_checkpoints_and_writes(tmp_path) -> None:
    checkpoint_path = tmp_path / "checkpoints.sqlite3"

    with SqliteSaver.from_conn_string(str(checkpoint_path)) as saver:
        _ensure_checkpoint_schema(saver)
        table_names = {
            row[0]
            for row in saver.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert {"checkpoints", "writes"} <= table_names
    assert "checkpointer" not in table_names


def test_checkpoint_history_is_bounded_per_thread_and_namespace(tmp_path) -> None:
    checkpoint_path = tmp_path / "checkpoints.sqlite3"
    cfg = replace(settings, memory_checkpoint_max_rows_per_thread=3)

    with SqliteSaver.from_conn_string(str(checkpoint_path)) as saver:
        saver.setup()
        saver.conn.executemany(
            """
            INSERT INTO checkpoints (
                thread_id,
                checkpoint_ns,
                checkpoint_id,
                parent_checkpoint_id,
                type,
                checkpoint,
                metadata
            ) VALUES (?, ?, ?, NULL, 'json', X'7B7D', X'7B7D')
            """,
            [("thread-1", "", f"{index:04d}") for index in range(10)],
        )
        saver.conn.executemany(
            """
            INSERT INTO writes (
                thread_id,
                checkpoint_ns,
                checkpoint_id,
                task_id,
                idx,
                channel,
                type,
                value
            ) VALUES (?, ?, ?, 'task-1', 0, 'channel-1', 'json', X'7B7D')
            """,
            [("thread-1", "", f"{index:04d}") for index in range(10)],
        )
        saver.conn.commit()

        checkpoint_rows, write_rows = _prune_checkpoint_history(saver, cfg)
        remaining_checkpoints = saver.conn.execute(
            "SELECT checkpoint_id FROM checkpoints ORDER BY checkpoint_id"
        ).fetchall()
        remaining_writes = saver.conn.execute(
            "SELECT checkpoint_id FROM writes ORDER BY checkpoint_id"
        ).fetchall()

    assert checkpoint_rows == 7
    assert write_rows == 7
    assert remaining_checkpoints == [("0007",), ("0008",), ("0009",)]
    assert remaining_writes == remaining_checkpoints


def test_failed_maintenance_retries_on_short_interval() -> None:
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    cfg = replace(settings, memory_maintenance_retry_minutes=15)
    state = {
        "last_errors": ["Checkpoint maintenance failed"],
        "last_maintenance_attempt_at": (now - timedelta(minutes=14)).isoformat(),
        "last_maintenance_at": (now - timedelta(days=2)).isoformat(),
    }

    assert not _maintenance_is_due(cfg, state, now=now)

    state["last_maintenance_attempt_at"] = (now - timedelta(minutes=15)).isoformat()
    assert _maintenance_is_due(cfg, state, now=now)


def test_startup_initialization_creates_both_databases(tmp_path) -> None:
    checkpoint_path = tmp_path / "memory" / "checkpoints.sqlite3"
    store_path = tmp_path / "memory" / "store.sqlite3"
    cfg = replace(
        settings,
        memory_checkpoint_db_path=checkpoint_path,
        memory_store_db_path=store_path,
        memory_maintenance_state_path=tmp_path / "memory" / "maintenance.json",
        memory_semantic_enabled=False,
        memory_setup=False,
        memory_maintenance_enabled=False,
    )

    assert initialize_coding_agent_memory(cfg)

    with sqlite3.connect(checkpoint_path) as conn:
        checkpoint_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    with sqlite3.connect(store_path) as conn:
        store_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert {"checkpoints", "writes"} <= checkpoint_tables
    assert store_tables


def test_vacuum_reclaims_deleted_pages(tmp_path) -> None:
    database_path = tmp_path / "large.sqlite3"
    with sqlite3.connect(database_path) as conn:
        conn.execute("CREATE TABLE payloads (value BLOB NOT NULL)")
        conn.executemany(
            "INSERT INTO payloads (value) VALUES (?)",
            [(b"x" * 8_192,) for _ in range(200)],
        )
        conn.commit()
        conn.execute("DELETE FROM payloads")
        conn.commit()

    before, after = _compact_sqlite_file(database_path)

    assert after < before
