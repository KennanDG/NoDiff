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
- [Vite's configuration](vite.config.ts) replaces the legacy `VITE_AI_AGENTS_API_BASE` and `VITE_AI_AGENTS_API_KEY` references with preload runtime values. A frontend `.env.local` is not needed for the normal desktop flow.
- `npm run dev` and `npm run desktop:dev` both run the Electron-enabled Vite setup. Opening the Vite URL in an ordinary browser does not provide the required desktop bridge. `npm run preview` serves built assets but does not create a complete desktop runtime.

## Workspace components

| Component | Responsibility |
| --- | --- |
| [`App.tsx`](src/App.tsx) | Repository selection, run state, streamed events, approval, and GitHub coordination |
| [`Sidebar.tsx`](src/components/Sidebar.tsx) | Repository tree and file selection |
| [`TaskPanel.tsx`](src/components/TaskPanel.tsx) | Typed/voice tasks, attachments, and conversation controls |
| [`DiffPanel.tsx`](src/components/DiffPanel.tsx) | Proposed changes and file review |
| [`OutputPanel.tsx`](src/components/OutputPanel.tsx) | Run output and reports |
| [`SourceControlPage.tsx`](src/components/SourceControlPage.tsx) | Managed GitHub branches, status, commits, pull/push, and PR creation |
| [`SkillsPage.tsx`](src/components/SkillsPage.tsx) | Coding/voice skills and custom tool administration |
| [`AgentSettingsModal.tsx`](src/components/AgentSettingsModal.tsx) | Provider/model selection, credentials, and execution budgets |
| [`src/lib/`](src/lib/) | Typed admin, repository, coding WebSocket, and voice clients |

## Commands

All commands below run from `frontend/`.

| Command | Behavior |
| --- | --- |
| `npm ci` | Install the committed npm dependency versions |
| `npm run desktop:dev` / `npm run dev` | Start Vite and Electron with a source backend |
| `npm run typecheck` | TypeScript project checks |
| `npm run build` | TypeScript checks plus renderer/main/preload build; no installer |
| `npm run preview` | Preview built Vite assets; does not supply the desktop bridge |
| `npm run backend:build:windows` | Freeze the backend with the committed PyInstaller spec |
| `npm run desktop:build:windows` | Build backend and frontend, then create x64 NSIS |
| `npm run desktop:build` | Alias for `desktop:build:windows` |
| `npm run desktop:build:store` | Build backend and frontend, then create x64 MSIX |

There is currently no `npm test` script. The installed Electron Builder version is pinned to `27.0.0-alpha.8`; use `npm ci` to preserve the packaging dependency set.

## Windows packaging

### Shared prerequisites

1. Build on Windows x64 with the source dependencies installed. The PyInstaller spec explicitly includes `sqlite_vec/vec0.dll`; it is not a cross-platform sidecar spec.
2. Supply **`frontend/build/icon.ico`**. Both packaging configurations reference it, but the file is absent from the tracked repository and `build/` is ignored. A fresh checkout therefore needs this resource before packaging.
3. Run packaging from `frontend/`. The build scripts create `backend/dist/nodiff-agent-runtime/` before Electron Builder copies it into `resources/backend/nodiff-agent-runtime/`.

For example, copy an existing NoDiff ICO file into the expected location, replacing the source path:

```powershell
New-Item -ItemType Directory -Force build | Out-Null
Copy-Item "C:\path\to\nodiff-icon.ico" "build\icon.ico"
```

The sidecar bundles Python, provider dependencies, SQLite resources, and built-in coding/voice skills and tool sources. Users still need Git for repository operations and the relevant project toolchains/dependencies for validation; these are not supplied by the app installer.

### NSIS installer

```powershell
npm run desktop:build:windows
```

The configured installer name is `release/NoDiff-<version>-x64-Setup.exe`. [package.json](package.json) currently declares app version `0.1.0`, product name `NoDiff`, and app ID `com.kennangauthier.nodiff`. The assisted installer supports choosing an installation directory and creating desktop/Start Menu shortcuts.

### Microsoft Store MSIX

Copy the exact product identity values from your reserved app in Partner Center into the following environment variables, then run:

```powershell
$env:MICROSOFT_STORE_IDENTITY_NAME = "<Package/Identity/Name>"
$env:MICROSOFT_STORE_PUBLISHER = "<Package/Identity/Publisher>"
$env:MICROSOFT_STORE_PUBLISHER_DISPLAY_NAME = "<Publisher display name>"
$env:MICROSOFT_STORE_VERSION = "1.0.0"
$env:MICROSOFT_STORE_DISPLAY_NAME = "NoDiff"
npm run desktop:build:store
```

The first three values are required by [electron-builder.store.cjs](electron-builder.store.cjs). `MICROSOFT_STORE_VERSION` defaults to `1.0.0` and accepts one to three numeric components with a nonzero major version; it overrides the package metadata for this build. The display name is optional and defaults to `NoDiff`.

The configured output is `release-store/NoDiff-<version>-x64.msix`, with minimum Windows version `10.0.17763.0`. Store artwork is tracked in [`assets/appx/`](assets/appx/), while the configured build-resource directory is `build/`; verify the actual packaged artwork when preparing a submission.

These scripts build packages. They do not submit to Partner Center or define a certificate-signing workflow. Signing/trust for local installation and Store release preparation are separate steps. A `Build-NoDiff-MSIX.ps1` helper is not included in the tracked repository.

### CI and release scope

[Windows package](../.github/workflows/windows-package.yml) runs on manual dispatch and pull requests that change backend/frontend files or the workflow itself. It installs dependencies, type-checks the frontend, builds NSIS, and uploads `NoDiff-Windows-x64` artifacts for 14 days. The workflow also needs the missing icon resource to be supplied. It does not build MSIX, publish GitHub releases, or submit to the Store.

Packaged startup currently supports Windows only. macOS/Linux packaging, automatic updates, and a full signing/release pipeline are not configured.

## Runtime data and credentials

Electron uses `%APPDATA%\NoDiff` as its Windows profile and `agent-runtime/` beneath it for backend state, unless `AGENT_RUNTIME_DATA_DIR` overrides the runtime root. It sets explicit paths for model configuration, the last local folder, GitHub workspaces, memory databases, and the embedding cache before spawning the backend.

Agent Settings applies new credentials to the running backend and sends them to the main process for encryption through Electron `safeStorage`. Encrypted values are saved in `runtime-secrets.json` and restored on future launches. Encryption must be available for this persistence step. Backend settings responses return configured flags rather than saved secret values.

The window opens after backend health succeeds. Normal shutdown sends `shutdown` to the sidecar's stdin and waits for it to exit, with a termination fallback.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Desktop cannot launch `uv` | Install `uv`, make it available on the launching shell's `PATH`, and run `uv sync --frozen` in `backend/` |
| Sidecar fails to initialize | Read the startup dialog and `logs/sidecar-startup.log` under the runtime root; it includes the launch command and recent backend output |
| First launch times out during memory setup | Run the [backend memory diagnostics](../backend/README.md#memory-and-diagnostics); the embedding cache may need its initial download |
| Backend request fails or hangs | Inspect `logs/runtime.log` and `logs/desktop-api.log`; slow/failed requests include diagnostic IDs |
| Ordinary browser tab cannot connect | Launch the Electron window with `npm run desktop:dev` so the preload runtime is present |
| Packaging cannot find the icon or sidecar | Supply `build/icon.ico` and use the full desktop build script so PyInstaller runs first |
| Agent validation cannot find pytest, Ruff, or npm | Install the required tools/dependencies for the selected project; the bundled sidecar is not its development environment |
| MSIX build reports missing identity values | Set the three required `MICROSOFT_STORE_*` identity variables in the same terminal as the build |

See Agent Settings for the resolved runtime directory, especially when Windows package path virtualization is involved.
