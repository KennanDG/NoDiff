"""Regression coverage for NoDiff runtime paths and first-launch persistence."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "src"


def run_isolated(tmp_path: Path, code: str, **overrides: str) -> None:
    # Isolate configuration imports so tests never initialize a user's real memory.
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("AGENT_RUNTIME_", "CODING_AGENT_MEMORY_"))
        and key not in {"ENV_FILE", "GITHUB_WORKSPACE_ROOT"}
    }
    env.update(
        ENV_FILE=str(tmp_path / "absent.env"),
        AGENT_RUNTIME_DATA_DIR=str(tmp_path / "runtime"),
        PYTHONPATH=os.pathsep.join(filter(None, [str(SOURCE), env.get("PYTHONPATH")])),
    )
    env.update(overrides)
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("first_import", [
    "agent_runtime.config.settings",
    "agent_runtime.agents.coding.coding_agent_settings",
])
def test_explicit_env_is_shared_in_either_import_order(tmp_path, first_import):
    env_file = tmp_path / "chosen.env"
    env_file.write_text(
        "CODING_AGENT_MEMORY_DIR=.agent-runtime/memory\n"
        "CODING_AGENT_MEMORY_EMBEDDING_CACHE_DIR=.agent-runtime/memory/fastembed-cache\n"
        "CODING_AGENT_MEMORY_SEMANTIC=false\n"
        "AGENT_RUNTIME_DATA_DIR=ignored-by-process-override\n",
        encoding="utf-8",
    )
    run_isolated(tmp_path, f'''
        import importlib
        importlib.import_module({first_import!r})
        from agent_runtime.config.settings import settings as runtime
        from agent_runtime.agents.coding.coding_agent_settings import settings as coding
        from pathlib import Path
        assert runtime.agent_runtime_data_dir == (Path.cwd() / 'runtime').resolve()
        assert coding.memory_checkpoint_db_path == runtime.agent_runtime_data_dir / 'memory/checkpoints.sqlite3'
        assert coding.memory_embedding_cache_dir == runtime.agent_runtime_data_dir / 'memory/fastembed-cache'
        assert not coding.memory_semantic_enabled
        assert coding.memory_setup
    ''', ENV_FILE=str(env_file))


def test_default_env_comes_from_backend_not_launch_directory(tmp_path):
    run_isolated(tmp_path, f'''
        import os, shutil, sys
        from pathlib import Path
        source = Path({str(SOURCE)!r})
        backend = Path.cwd() / 'fixture/backend'
        root = backend / 'src'
        for relative in ('agent_runtime/config/settings.py', 'agent_runtime/agents/coding/coding_agent_settings.py'):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, target)
            parent = target.parent
            while parent != root:
                (parent / '__init__.py').touch()
                parent = parent.parent
        (backend / '.env').write_text('CODING_AGENT_MEMORY_SEMANTIC=false\\n', encoding='utf-8')
        (Path.cwd() / '.env').write_text('CODING_AGENT_MEMORY_SEMANTIC=true\\n', encoding='utf-8')
        os.environ.pop('ENV_FILE')
        sys.path.insert(0, str(root))
        from agent_runtime.agents.coding.coding_agent_settings import settings
        assert not settings.memory_semantic_enabled
    ''')


def test_absolute_override_and_legacy_relative_children(tmp_path):
    run_isolated(tmp_path, '''
        from pathlib import Path
        from agent_runtime.config.settings import _resolve_runtime_path
        root = Path.cwd() / 'runtime'
        external = Path.cwd() / 'custom/cache'
        assert _resolve_runtime_path(external, root) == external
        assert _resolve_runtime_path('.agent-runtime/memory/store.sqlite3', root) == root / 'memory/store.sqlite3'
        assert _resolve_runtime_path('.agent-runtime/.agent-runtime/memory', root) == root / 'memory'
        assert _resolve_runtime_path('memory', root) == root / 'memory'
        # The root override itself remains an explicit user choice.
        assert _resolve_runtime_path('.agent-runtime', root, legacy_relative=False) == root / '.agent-runtime'
    ''')


def test_nested_legacy_database_is_copied_without_overwriting(tmp_path):
    run_isolated(tmp_path, '''
        import sqlite3
        from pathlib import Path
        from agent_runtime.config.settings import Settings, initialize_runtime_data_layout
        root = Path.cwd() / 'migration'
        source = root / '.agent-runtime/memory/store.sqlite3'
        source.parent.mkdir(parents=True)
        with sqlite3.connect(source) as conn:
            conn.execute('create table marker (value text)')
            conn.execute("insert into marker values ('legacy')")
        cfg = Settings(AGENT_RUNTIME_DATA_DIR=root, _env_file=None)
        initialize_runtime_data_layout(cfg)
        dest = cfg.agent_runtime_data_dir / 'memory/store.sqlite3'
        with sqlite3.connect(dest) as conn:
            assert conn.execute('select value from marker').fetchone() == ('legacy',)
            conn.execute("update marker set value='current'")
        initialize_runtime_data_layout(cfg)
        with sqlite3.connect(dest) as conn:
            assert conn.execute('select value from marker').fetchone() == ('current',)
        assert source.exists()
    ''')


def test_fresh_sqlite_initialization_is_idempotent_and_persistent(tmp_path):
    run_isolated(tmp_path, '''
        from dataclasses import replace
        from agent_runtime.agents.coding import memory
        cfg = replace(memory.default_settings, memory_semantic_enabled=False,
                      memory_maintenance_enabled=False, memory_vacuum_enabled=False)
        assert memory.initialize_coding_agent_memory(cfg)
        assert memory.initialize_coding_agent_memory(cfg)
        assert cfg.memory_checkpoint_db_path.is_file()
        assert cfg.memory_store_db_path.is_file()
        with memory.coding_agent_persistence(cfg, setup=False) as persistence:
            persistence.store.put(('startup_test',), 'key', {'text': 'remember me'})
        with memory.coding_agent_persistence(cfg, setup=False) as persistence:
            assert persistence.store.get(('startup_test',), 'key').value['text'] == 'remember me'
    ''')


def test_fresh_cache_supports_metadata_rename_and_model_initialization(tmp_path):
    run_isolated(tmp_path, '''
        from pathlib import Path
        from agent_runtime.agents.coding import memory
        captured = {}
        class FakeEmbeddings:
            def __init__(self, **kwargs):
                captured.update(kwargs)
                cache = Path(kwargs['cache_dir'])
                assert cache.is_dir()
                assert not list(cache.glob('.nodiff-*'))
                # Simulate the exact deep Hugging Face tree-cache write.
                trees = cache / ('models--' + 'x' * 100) / ('s' * 100) / 'trees'
                trees.mkdir(parents=True)
                temporary = trees / 'download.tmp'
                temporary.write_text('{}', encoding='utf-8')
                destination = trees / ('a' * 40 + '.json')
                assert len(str(destination)) > 260
                temporary.replace(destination)
                assert destination.read_text() == '{}'
        memory.FastEmbedEmbeddings = FakeEmbeddings
        config = memory._memory_index_config(memory.default_settings)
        assert config['dims'] == 384
        assert captured['model_name'] == 'BAAI/bge-small-en-v1.5'
    ''')


def test_failed_model_keeps_original_error_and_cache_diagnostic(tmp_path):
    run_isolated(tmp_path, '''
        from agent_runtime.agents.coding import memory
        failure = FileNotFoundError('missing model snapshot')
        def fail(**kwargs):
            raise failure
        memory.FastEmbedEmbeddings = fail
        try:
            memory.initialize_coding_agent_memory()
        except RuntimeError as exc:
            assert exc.__cause__ is failure
            assert str(memory.default_settings.memory_embedding_cache_dir) in str(exc)
        else:
            raise AssertionError('Semantic initialization must not silently succeed')
    ''')


def test_windows_extended_paths_cover_drive_unc_and_existing_prefix(tmp_path):
    run_isolated(tmp_path, r'''
        from types import SimpleNamespace
        from agent_runtime.agents.coding import memory
        original_os = memory.os
        memory.os = SimpleNamespace(name='nt')
        try:
            convert = memory._windows_extended_path
            assert convert(r'C:\Users\Name\cache') == '\\\\?\\C:\\Users\\Name\\cache'
            assert convert(r'\\server\share\cache') == '\\\\?\\UNC\\server\\share\\cache'
            prefixed = '\\\\?\\C:\\cache'
            assert convert(prefixed) == prefixed
        finally:
            memory.os = original_os
    ''')
