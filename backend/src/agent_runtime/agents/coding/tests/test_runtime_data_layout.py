from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from agent_runtime.config.settings import Settings, initialize_runtime_data_layout


def _settings_for(runtime_root: Path) -> Settings:
    return Settings(
        _env_file=None,
        AGENT_RUNTIME_DATA_DIR=runtime_root,
    )


def test_all_default_mutable_paths_share_runtime_root(tmp_path: Path) -> None:
    runtime_root = tmp_path / "NoDiff" / "agent-runtime"
    config = _settings_for(runtime_root)

    assert config.agent_runtime_data_dir == runtime_root.resolve()
    assert config.runtime_agent_config_path == runtime_root / "runtime-agent-config.json"
    assert config.local_repository_session_path == (
        runtime_root / "local-repository-session.json"
    )
    assert config.github_workspace_root == runtime_root / "github-workspaces"


def test_relative_child_overrides_are_anchored_to_runtime_root(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    config = Settings(
        _env_file=None,
        AGENT_RUNTIME_DATA_DIR=runtime_root,
        AGENT_RUNTIME_CONFIG_PATH=Path("configuration/models.json"),
        AGENT_RUNTIME_LOCAL_REPOSITORY_SESSION_PATH=Path("sessions/local.json"),
        GITHUB_WORKSPACE_ROOT=Path("workspaces/github"),
    )

    assert config.runtime_agent_config_path == runtime_root / "configuration/models.json"
    assert config.local_repository_session_path == runtime_root / "sessions/local.json"
    assert config.github_workspace_root == runtime_root / "workspaces/github"


def test_legacy_runtime_state_is_copied_once_without_overwriting(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    legacy_root = project / ".agent-runtime"
    legacy_memory = legacy_root / "memory"
    legacy_memory.mkdir(parents=True)
    (legacy_root / "runtime-agent-config.json").write_text(
        json.dumps({"coding_model": "legacy-model"}),
        encoding="utf-8",
    )
    (legacy_root / "local-repository-session.json").write_text(
        json.dumps({"repo_root": str(project)}),
        encoding="utf-8",
    )
    with sqlite3.connect(legacy_memory / "checkpoints.sqlite3") as connection:
        connection.execute("CREATE TABLE migrated (value TEXT NOT NULL)")
        connection.execute("INSERT INTO migrated VALUES ('yes')")
        connection.commit()

    monkeypatch.chdir(project)
    runtime_root = tmp_path / "app-data" / "NoDiff" / "agent-runtime"
    config = _settings_for(runtime_root)
    initialize_runtime_data_layout(config)

    assert json.loads(config.runtime_agent_config_path.read_text(encoding="utf-8")) == {
        "coding_model": "legacy-model"
    }
    assert config.local_repository_session_path.is_file()
    with sqlite3.connect(runtime_root / "memory" / "checkpoints.sqlite3") as connection:
        assert connection.execute("SELECT value FROM migrated").fetchone() == ("yes",)

    config.runtime_agent_config_path.write_text("canonical", encoding="utf-8")
    initialize_runtime_data_layout(config)
    assert config.runtime_agent_config_path.read_text(encoding="utf-8") == "canonical"
