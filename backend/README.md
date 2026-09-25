# NoDiff agent runtime

The `nodiff-agent-runtime` Python package provides NoDiff's FastAPI API, LangGraph coding and voice workflows, local memory, model configuration, GitHub operations, and skill/tool registries. The import namespace is `agent_runtime`.

For the normal desktop workflow, follow the [project quick start](../README.md#run-the-desktop-app-from-source). Electron launches and stops this runtime automatically. This guide covers direct API development and backend internals.

## Install

Python **3.10–3.13** is supported by [pyproject.toml](pyproject.toml); the Windows packaging workflow uses Python **3.13**. From `backend/`:

```powershell
uv sync --frozen
```

The default sync includes the `dev` group with pytest, Ruff, and mypy. Git must be installed for GitHub checkout operations. The runtime also relies on each selected repository's own build/test dependencies.

## Run the API directly

The source runtime reads `backend/.env` regardless of the launching directory. `ENV_FILE` can select a different dotenv file; already-set process variables take precedence. Frozen builds normally receive their environment from Electron and do not search for a source `.env`.

Create `backend/.env` with the credentials you need. The following is an example for the repository's default model providers; replace placeholders:

```dotenv
AGENT_RUNTIME_API_KEY=replace-with-a-long-random-local-key
GROQ_API_KEY=your-groq-key
DEEPSEEK_API_KEY=your-deepseek-key

# Optional integrations
# GITHUB_TOKEN=your-github-token
# GITHUB_TOKEN_KIND=user
# SERPAPI_API_KEY=your-serpapi-key
```

For a direct Windows API launch, explicitly set the runtime root so custom registries and core settings use the same directory:

```powershell
$env:AGENT_RUNTIME_DATA_DIR = Join-Path $env:APPDATA "NoDiff\agent-runtime"
uv run python -m agent_runtime.api.main
```

For a POSIX shell, set an absolute writable directory before the same module command:

```bash
export AGENT_RUNTIME_DATA_DIR="$HOME/.config/NoDiff/agent-runtime"
uv run python -m agent_runtime.api.main
```

The direct API defaults to `127.0.0.1:8765`; `AGENT_RUNTIME_HOST` and `AGENT_RUNTIME_PORT` override these. Keep the interactive terminal open: this entrypoint monitors stdin for `shutdown` or EOF to support its desktop sidecar lifecycle.

`/health`, `/docs`, and `/openapi.json` are public local endpoints. Other HTTP routes require the `x-api-key` header. The API is intended for local, single-user use. Starting it separately does not attach the current Electron launcher to it; Electron starts its own managed backend.

### API routes

| Route/prefix | Purpose |
| --- | --- |
| `/health` | Liveness/readiness after application startup |
| `/coding-agent/repository/tree` and `/coding-agent/repository/file` | Repository inspection |
| `/coding-agent/ws` | Coding requests, streamed events, approval, and rejection |
| `/coding-agent/token` | Authenticated issuance of a short-lived, single-use WebSocket token |
| `/voice-agent/turn` | Multipart audio turn with conversation/attachment context |
| `/github` | Connection, discovery, imports, branches, status, pull, commit, push, and PRs |
| `/admin` | Local repository session, model catalogs/settings, skills, and tools |

The current desktop WebSocket client sends `api_key` in the connection query. The backend also accepts an `x-api-key` header or a single-use `token` that expires after 60 seconds. Interactive API documentation is at `http://127.0.0.1:8765/docs` for a default direct launch; Electron-managed ports are dynamic.

## Configuration and persistence

[settings.py](src/agent_runtime/config/settings.py) defines provider credentials, model slots, API paths, voice options, and GitHub limits. [coding_agent_settings.py](src/agent_runtime/agents/coding/coding_agent_settings.py) defines coding, context, shell, and memory controls.

| Environment variable | Purpose |
| --- | --- |
| `AGENT_RUNTIME_DATA_DIR` | Writable runtime root; set explicitly for direct launches |
| `AGENT_RUNTIME_API_KEY` | API authentication; generated automatically only by the desktop launcher |
| `AGENT_RUNTIME_HOST`, `AGENT_RUNTIME_PORT` | Direct-launch listener; defaults to `127.0.0.1:8765` |
| `AGENT_RUNTIME_ALLOWED_ORIGINS` | Additional configured renderer origins; local loopback and packaged renderer origins are also allowed by the API |
| `GROQ_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` | Credentials for selected model providers |
| `CODING_PROVIDER`, `CODING_MODEL`, `REASONING_PROVIDER`, `REASONING_MODEL` | Coding and reconciliation model slots |
| `CAPTION_PROVIDER`, `CAPTION_MODEL` | Vision/captioning slot |
| `VOICE_CHAT_PROVIDER`, `VOICE_CHAT_MODEL` | Voice conversation slot |
| `VOICE_STT_PROVIDER`, `VOICE_STT_MODEL`, `VOICE_TTS_PROVIDER`, `VOICE_TTS_MODEL` | Speech providers/models |
| `VOICE_TTS_ENABLED` | Enable/disable synthesized speech; defaults to `true` |
| `GITHUB_TOKEN`, `GITHUB_TOKEN_KIND` | GitHub credential and `user`/`installation` token mode |
| `SERPAPI_API_KEY` | Built-in web search credential |

Non-secret model settings are saved in `runtime-agent-config.json`; coding limits are saved separately in `runtime-agent-config-coding-runtime.json`. Saved selections are loaded on startup and can supersede environment defaults. The last valid local repository is saved in `local-repository-session.json`, and managed GitHub clones live in `github-workspaces/`.

Core settings default to the platform application-data directory under `NoDiff/agent-runtime`. **Direct-launch caveat:** custom skill/tool registries fall back to `~/.nodiff/agent-runtime` if `AGENT_RUNTIME_DATA_DIR` is absent. Explicitly setting the variable avoids split storage; Electron already sets it and its child paths.

Credentials submitted to the admin API affect the current backend process and are not written into the non-secret configuration files. Desktop credential persistence is a separate Electron `safeStorage` feature; the backend by itself does not decrypt `runtime-secrets.json`.

The FastAPI entrypoint disables LangSmith tracing before importing agent routers. Tracing environment flags do not re-enable it in this configuration.

## Coding and validation

The [coding graph](src/agent_runtime/agents/coding/graph.py) performs routing and memory recall, planning, optional web search/custom-tool context, repository navigation, dependency-ready implementation workers, reconciliation, validation, bounded repair, reporting, and durable outcome storage.

Defaults include 3 concurrent workers, up to 12 implementation units, 1 patch retry per unit, and 2 implementation iterations. The coding-model slot produces worker proposals; the reasoning slot is used for conditional reconciliation. Multiple skills can inform a run.

The WebSocket API stages runs in a temporary workspace copy. Writable runs require a later approval message before their generated files are copied to the original repository. A dry run produces proposals without applying them or validating the proposed edits. Custom tools and validation commands still execute locally; the temporary workspace is not process isolation.

The writer handles UTF-8 text without a Python/TypeScript-only extension restriction. Binary generation and general-purpose language-specific validation are not implemented. Write restrictions still apply to protected directories, selected environment files, and lockfiles.

Validation uses targeted/requested commands or fallback profiles. The Python runtime resolver checks a project `.venv`/`venv`, then `uv`, then a suitable system Python. The frozen sidecar excludes pytest, mypy, and Ruff; install validation tools in the selected project's environment. npm/npx checks likewise require the project's Node toolchain and dependencies. Automatic frontend discovery still contains the legacy `agents/frontend` path, so do not assume it discovers every repository layout; inspect the commands reported by the run.

## Skills and tool contract

Built-in resources live under `agents/coding/skills`, `agents/coding/tools`, `agents/voice/skills`, and `agents/voice/tools` within `src/agent_runtime/`. Custom resources use the corresponding `agents/<agent>/` paths under `AGENT_RUNTIME_DATA_DIR`:

| Relative path | Purpose |
| --- | --- |
| `agents/<agent>/skills/` | Custom Markdown skill overlays |
| `agents/<agent>/tools/custom_pending/` | Tool drafts awaiting review |
| `agents/<agent>/tools/custom_approved/` | Approved executable tools |

The shared skill registry reads built-ins and overlays from disk. Skills declare executable tool names in an `Allowed tools` section. Admin endpoints support authoring, import/normalization, AI generation, and custom-resource management.

A custom tool module must define a **synchronous function with the tool's exact name**. Named parameters and `**kwargs` are supported; positional-only parameters and `*args` are rejected. Helper functions/classes and imports from the standard library, available third-party packages, and existing NoDiff tools are allowed.

Syntax/entrypoint/signature checks are enforced. Powerful Python operations and import-time execution are reported for review rather than prohibited by the source validator. Approval imports the candidate to validate runtime compatibility, so code review also needs to cover module-level execution. Approved tools run with backend privileges, and their dependencies must already exist in the installed/frozen runtime. Invocation count and result size are bounded; this is not an OS sandbox.

## Memory and diagnostics

Coding memory uses local SQLite checkpoints and a local durable store, with FastEmbed semantic retrieval. The default model is `BAAI/bge-small-en-v1.5` with 384-dimensional vectors. The first initialization may download model files; subsequent use reads the cache under `memory/fastembed-cache/`.

| Path under the runtime root | Purpose |
| --- | --- |
| `memory/checkpoints.sqlite3` | Thread-scoped graph checkpoints |
| `memory/store.sqlite3` | Repository-scoped cross-thread outcomes |
| `memory/fastembed-cache/` | Embedding model/cache |
| `memory/maintenance.json` | Maintenance scheduling state |
| `logs/runtime.log` | Rotating API/backend diagnostics |

Default maintenance runs opportunistically when persistence opens. It retains up to 100 checkpoint threads with a 30-day age policy and limits each thread/namespace to 50 recent checkpoints. Durable memories use a 365-day policy, a 300-item cap per repository namespace, and a minimum recent set of 25. Deduplication, conservative consolidation, WAL checkpointing, and periodic vacuuming manage database growth.

Startup initializes memory by default and fails if initialization fails (`AGENT_RUNTIME_INITIALIZE_MEMORY_ON_STARTUP=true`, `AGENT_RUNTIME_MEMORY_INIT_STRICT=true`). From `backend/`, check the actual paths, SQLite setup, and embedding cache with:

```powershell
uv run python scripts/diagnose_memory.py --sqlite-only
uv run python scripts/diagnose_memory.py
```

The first command skips the embedding model. The second initializes it and can complete the first download before the desktop's 45-second readiness timeout becomes relevant. Both disable pruning/compaction for the diagnostic run. Use the same `AGENT_RUNTIME_DATA_DIR` as the desktop if you override it.

The desktop also writes `logs/sidecar-startup.log` for initialization failures and `logs/desktop-api.log` for slow or failed bridged requests. The resolved runtime root is shown in Agent Settings and in diagnostics.

## Checks

From `backend/`:

```powershell
uv run ruff check src tests
uv run pytest tests src/agent_runtime/agents/coding/tests src/agent_runtime/agents/voice/tests
```

Explicit paths are needed to include agent tests: the configured default `testpaths` is only `tests/`. These commands describe the available checks, not a green CI guarantee. The Windows packaging workflow does not currently run them.

## Standalone coding CLI

The CLI is separate from the desktop/API approval lifecycle. It defaults to a dry run; `--write` permits writes directly to the selected repository without a subsequent desktop approval step.

The current [CLI module](src/agent_runtime/agents/coding/main.py) still reads `LANGCHAIN_API_KEY` eagerly. It must be present even if tracing is disabled; unlike the API entrypoint, the CLI does not use the tracing-disable bootstrap. Set tracing flags explicitly when running it.

From `backend/`, after setting the required environment and provider credentials:

```powershell
uv run python -m agent_runtime.agents.coding.main --repo-root "C:\path\to\repository" --workspace-root "C:\path\to\repository" "Explain how validation is selected for this project"
```

`--markdown-report` or `--report-path` writes a report, `--thread-id` reuses a checkpoint thread, and `--no-memory` disables persistence for that invocation. Some CLI help text still mentions Postgres; the active memory implementation is SQLite.

## Freeze the Windows sidecar

On Windows, from `backend/`:

```powershell
uv run pyinstaller --noconfirm --clean nodiff-agent-runtime.spec
```

The output is `dist/nodiff-agent-runtime/nodiff-agent-runtime.exe` with its supporting directory. The spec collects dynamic provider dependencies, SQLite resources including `sqlite_vec/vec0.dll`, and physical built-in skill/tool files needed by the disk-scanning registries. It excludes pending/approved custom tools and development-only tools.

Use the [frontend packaging scripts](../frontend/README.md#windows-packaging) to include the entire sidecar directory in NSIS/MSIX artifacts.
