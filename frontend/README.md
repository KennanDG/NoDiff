# NoDiff desktop frontend

The live NoDiff desktop client uses React 19, TypeScript, Vite, Electron, Tailwind CSS, and Monaco Editor. It connects to the local FastAPI runtime for coding, voice, settings, skills/tools, and GitHub operations.

See the [project README](../README.md) for the feature overview and the [backend README](../backend/README.md) for runtime configuration.

## Develop locally

Install Python 3.10–3.13, `uv`, Node.js/npm, and Git. The Windows build workflow uses Python 3.13 and Node.js 22. First install backend dependencies from `backend/` with `uv sync --frozen`, then run from this directory:

```powershell
npm ci
npm run desktop:dev
```

Keep `uv` on the launching shell's `PATH`. Electron starts `uv run python -m agent_runtime.api.main` in `backend/`, waits up to 45 seconds for `/health`, then opens the window. On Windows, use a native Windows backend and frontend together so the directory picker returns usable paths.

Configure models and credentials in **Agent Settings**. Source runs can also read provider credentials from `backend/.env`; Electron supplies the runtime connection and data paths itself.

### Desktop connection

- The main process binds the backend to `127.0.0.1`, chooses a free port unless `AGENT_RUNTIME_PORT` is set, and generates an API key unless `AGENT_RUNTIME_API_KEY` is supplied.
- The context-isolated preload exposes `window.desktop.runtime`, directory selection, a restricted HTTP request bridge, and encrypted credential persistence.
- Admin and repository clients use the desktop HTTP bridge when available. Coding progress uses a direct WebSocket connection; voice turns use multipart HTTP requests.
- [Vite&#39;s configuration](vite.config.ts) replaces the legacy `VITE_AI_AGENTS_API_BASE` and `VITE_AI_AGENTS_API_KEY` references with preload runtime values. A frontend `.env.local` is not needed for the normal desktop flow.
- `npm run dev` and `npm run desktop:dev` both run the Electron-enabled Vite setup. Opening the Vite URL in an ordinary browser does not provide the required desktop bridge. `npm run preview` serves built assets but does not create a complete desktop runtime.

## Workspace components

| Component                                                          | Responsibility                                                       |
| ------------------------------------------------------------------ | -------------------------------------------------------------------- |
| [`App.tsx`](src/App.tsx)                                          | Main container for frontend components                               |
| [`Sidebar.tsx`](src/components/Sidebar.tsx)                       | Repository tree and file selection                                   |
| [`TaskPanel.tsx`](src/components/TaskPanel.tsx)                   | Typed/voice tasks, attachments, and conversation controls            |
| [`DiffPanel.tsx`](src/components/DiffPanel.tsx)                   | Proposed changes and file review                                     |
| [`OutputPanel.tsx`](src/components/OutputPanel.tsx)               | Run output and reports                                               |
| [`SourceControlPage.tsx`](src/components/SourceControlPage.tsx)   | Managed GitHub branches, status, commits, pull/push, and PR creation |
| [`SkillsPage.tsx`](src/components/SkillsPage.tsx)                 | Coding/voice skills and custom tool administration                   |
| [`AgentSettingsModal.tsx`](src/components/AgentSettingsModal.tsx) | Provider/model selection, credentials, and execution budgets         |
| [`src/lib/`](src/lib/)                                            | Frontend API Contract                                                |

## Commands

All commands below run from `frontend/`.

| Command                                   | Behavior                                                         |
| ----------------------------------------- | ---------------------------------------------------------------- |
| `npm ci`                                | Install the committed npm dependency versions                    |
| `npm run desktop:dev` / `npm run dev` | Start Vite and Electron with a source backend                    |
| `npm run typecheck`                     | TypeScript project checks                                        |
| `npm run build`                         | TypeScript checks plus renderer/main/preload build; no installer |
| `npm run preview`                       | Preview built Vite assets; does not supply the desktop bridge    |

There is currently no `npm test` script. The installed Electron Builder version is pinned to `27.0.0-alpha.8`; use `npm ci` to preserve the packaging dependency set.

## Runtime data and credentials

Electron uses `%APPDATA%\NoDiff` as its Windows profile and `agent-runtime/` beneath it for backend state, unless `AGENT_RUNTIME_DATA_DIR` overrides the runtime root. It sets explicit paths for model configuration, the last local folder, GitHub workspaces, memory databases, and the embedding cache before spawning the backend.

Agent Settings applies new credentials to the running backend and sends them to the main process for encryption through Electron `safeStorage`. Encrypted values are saved in `runtime-secrets.json` and restored on future launches. Encryption must be available for this persistence step. Backend settings responses return configured flags rather than saved secret values.

The window opens after backend health succeeds. Normal shutdown sends `shutdown` to the sidecar's stdin and waits for it to exit, with a termination fallback.

## Troubleshooting

| Symptom                                           | Check                                                                                                                                    |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Desktop cannot launch`uv`                       | Install`uv`, make it available on the launching shell's `PATH`, and run `uv sync --frozen` in `backend/`                         |
| Sidecar fails to initialize                       | Read the startup dialog and`logs/sidecar-startup.log` under the runtime root; it includes the launch command and recent backend output |
| First launch times out during memory setup        | Run the[backend memory diagnostics](../backend/README.md#memory-and-diagnostics); the embedding cache may need its initial download       |
| Backend request fails or hangs                    | Inspect`logs/runtime.log` and `logs/desktop-api.log`; slow/failed requests include diagnostic IDs                                    |
| Ordinary browser tab cannot connect               | Launch the Electron window with`npm run desktop:dev` so the preload runtime is present                                                 |
| Packaging cannot find the icon or sidecar         | Supply`build/icon.ico` and use the full desktop build script so PyInstaller runs first                                                 |
| Agent validation cannot find pytest, Ruff, or npm | Install the required tools/dependencies for the selected project; the bundled sidecar is not its development environment                 |

See Agent Settings for the resolved runtime directory, especially when Windows package path virtualization is involved.
