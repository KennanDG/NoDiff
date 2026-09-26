import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { randomBytes } from "node:crypto";
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  statSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import { createServer } from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  safeStorage,
  shell,
  type OpenDialogOptions,
} from "electron";

const currentDirectory = path.dirname(fileURLToPath(import.meta.url));
const applicationRoot = path.join(currentDirectory, "..");
const developmentServerUrl = process.env.VITE_DEV_SERVER_URL;
const applicationDataDirectory = path.join(app.getPath("appData"), "NoDiff");
const backendSourceDirectory = path.resolve(applicationRoot, "..", "backend");

// Pin Electron's own profile to the product name before ready. The agent runtime
// uses a dedicated child so Chromium cache/storage and backend state never mix.
mkdirSync(applicationDataDirectory, { recursive: true });
app.setPath("userData", applicationDataDirectory);

const configuredRuntimeDataDirectory =
  process.env.AGENT_RUNTIME_DATA_DIR?.trim();
const runtimeDataDirectory = configuredRuntimeDataDirectory
  ? path.resolve(configuredRuntimeDataDirectory)
  : path.join(applicationDataDirectory, "agent-runtime");
const memoryDirectory = path.join(runtimeDataDirectory, "memory");

function logDesktopApi(message: string) {
  try {
    const directory = path.join(runtimeDataDirectory, "logs");
    mkdirSync(directory, { recursive: true });
    const file = path.join(directory, "desktop-api.log");
    if (existsSync(file) && statSync(file).size > 2_000_000) {
      renameSync(file, path.join(directory, "desktop-api.previous.log"));
    }
    appendFileSync(file, `${new Date().toISOString()} ${redactRuntimeSecrets(message)}\n`, "utf8");
  } catch (error) {
    console.error("Unable to write desktop API diagnostic log", error);
  }
}

const PERSISTENT_SECRET_ENV_KEYS = new Set([
  "GROQ_API_KEY",
  "DEEPSEEK_API_KEY",
  "OPENROUTER_API_KEY",
  "OPENAI_API_KEY",
  "ANTHROPIC_API_KEY",
  "GOOGLE_API_KEY",
  "GITHUB_TOKEN",
  "SERPAPI_API_KEY",
]);

const runtimeSecretsPath = path.join(
  runtimeDataDirectory,
  "runtime-secrets.json",
);

type PersistedSecretsFile = {
  version: 1;
  secrets: Record<string, string>;
};

type DesktopDirectoryPickerOptions = {
  title?: string;
  defaultPath?: string;
};

type DesktopApiRequest = {
  url: string;
  method?: string;
  headers?: Record<string, string>;
  body?: string | null;
  timeoutMs?: number;
};

type DesktopApiResponse = {
  status: number;
  statusText: string;
  ok: boolean;
  headers: Record<string, string>;
  body: string;
};

type SidecarLaunch = {
  command: string;
  args: string[];
  cwd: string;
};

let backendSidecar: ChildProcessWithoutNullStreams | null = null;
let backendShutdownPromise: Promise<void> | null = null;
let quitAfterBackendStops = false;

const SIDECAR_DIAGNOSTIC_TAIL_LENGTH = 12_000;
const SIDECAR_DIALOG_OUTPUT_LENGTH = 4_000;

let activeSidecarLaunch: SidecarLaunch | null = null;
let backendStdoutTail = "";
let backendStderrTail = "";
let backendSpawnError: Error | null = null;
let backendExitCode: number | null = null;
let backendExitSignal: NodeJS.Signals | null = null;
let backendClosePromise: Promise<void> | null = null;


function loadPersistentRuntimeSecrets() {
  if (!existsSync(runtimeSecretsPath)) return;

  if (!safeStorage.isEncryptionAvailable()) {
    console.warn(
      "OS-backed secret encryption is unavailable; persisted NoDiff credentials were not loaded.",
    );
    return;
  }

  try {
    const raw = JSON.parse(
      readFileSync(runtimeSecretsPath, "utf8"),
    ) as PersistedSecretsFile;

    if (
      raw?.version !== 1 ||
      !raw.secrets ||
      typeof raw.secrets !== "object"
    ) {
      return;
    }

    for (const [environmentName, encrypted] of Object.entries(raw.secrets)) {
      if (!PERSISTENT_SECRET_ENV_KEYS.has(environmentName)) continue;
      if (typeof encrypted !== "string" || !encrypted) continue;

      try {
        const value = safeStorage.decryptString(
          Buffer.from(encrypted, "base64"),
        );

        if (value) {
          process.env[environmentName] = value;
        }
      } catch (error) {
        console.error(
          `Unable to decrypt persisted credential ${environmentName}`,
          error,
        );
      }
    }
  } catch (error) {
    console.error("Unable to load persisted NoDiff credentials", error);
  }
}

function persistRuntimeSecrets(
  values: Record<string, string>,
) {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error(
      "OS-backed credential encryption is not available on this system.",
    );
  }

  let current: PersistedSecretsFile = {
    version: 1,
    secrets: {},
  };

  if (existsSync(runtimeSecretsPath)) {
    try {
      const parsed = JSON.parse(
        readFileSync(runtimeSecretsPath, "utf8"),
      ) as PersistedSecretsFile;

      if (
        parsed?.version === 1 &&
        parsed.secrets &&
        typeof parsed.secrets === "object"
      ) {
        current = parsed;
      }
    } catch {
      // Replace malformed state with a new credential file.
    }
  }

  for (const [environmentName, rawValue] of Object.entries(values)) {
    if (!PERSISTENT_SECRET_ENV_KEYS.has(environmentName)) {
      throw new Error(
        `Unsupported persistent runtime credential: ${environmentName}`,
      );
    }

    const value = rawValue.trim();
    if (!value) continue;

    current.secrets[environmentName] = safeStorage
      .encryptString(value)
      .toString("base64");

    // Keep the running Electron process synchronized too.
    process.env[environmentName] = value;
  }

  mkdirSync(path.dirname(runtimeSecretsPath), { recursive: true });

  writeFileSync(
    runtimeSecretsPath,
    JSON.stringify(current, null, 2),
    "utf8",
  );
}


function redactRuntimeSecrets(value: string) {
  const apiKey = process.env.AGENT_RUNTIME_API_KEY;
  return apiKey ? value.replaceAll(apiKey, "<redacted>") : value;
}


function appendDiagnosticTail(current: string, chunk: Buffer | string) {
  const next = current + chunk.toString();
  return next.length > SIDECAR_DIAGNOSTIC_TAIL_LENGTH
    ? next.slice(-SIDECAR_DIAGNOSTIC_TAIL_LENGTH)
    : next;
}


function writeSidecarDiagnosticLog(startupError: unknown): string | null {
  try {
    const logDirectory = path.join(runtimeDataDirectory, "logs");
    mkdirSync(logDirectory, { recursive: true });

    const logPath = path.join(logDirectory, "sidecar-startup.log");
    const launch = activeSidecarLaunch;
    const errorText =
      startupError instanceof Error
        ? `${startupError.name}: ${startupError.message}\n${startupError.stack ?? ""}`
        : String(startupError);

    const content = [
      `Timestamp: ${new Date().toISOString()}`,
      `NoDiff version: ${app.getVersion()}`,
      `Packaged: ${String(app.isPackaged)}`,
      `Platform: ${process.platform} ${process.arch}`,
      `Resources path: ${process.resourcesPath}`,
      `Runtime data directory: ${runtimeDataDirectory}`,
      `Runtime URL: ${process.env.AGENT_RUNTIME_API_BASE_URL ?? "(not configured)"}`,
      `Command: ${launch?.command ?? "(not resolved)"}`,
      `Arguments: ${launch?.args.join(" ") || "(none)"}`,
      `Working directory: ${launch?.cwd ?? "(not resolved)"}`,
      `Exit code: ${backendExitCode ?? backendSidecar?.exitCode ?? "(none)"}`,
      `Exit signal: ${backendExitSignal ?? backendSidecar?.signalCode ?? "(none)"}`,
      `Spawn error: ${backendSpawnError?.message ?? "(none)"}`,
      "",
      "--- Startup error ---",
      errorText,
      "",
      "--- stderr (tail) ---",
      backendStderrTail.trim() || "(no stderr captured)",
      "",
      "--- stdout (tail) ---",
      backendStdoutTail.trim() || "(no stdout captured)",
      "",
    ].join("\n");

    writeFileSync(logPath, redactRuntimeSecrets(content), "utf8");
    return logPath;
  } catch (error) {
    console.error("Unable to write FastAPI sidecar diagnostic log", error);
    return null;
  }
}

function formatSidecarStartupFailure(
  startupError: unknown,
  diagnosticLogPath: string | null,
) {
  const launch = activeSidecarLaunch;
  const startupMessage =
    startupError instanceof Error ? startupError.message : String(startupError);

  const output = (backendStderrTail.trim() || backendStdoutTail.trim()).slice(
    -SIDECAR_DIALOG_OUTPUT_LENGTH,
  );

  const details = [
    `Startup error: ${startupMessage}`,
    "",
    "Process diagnostics:",
    `Executable: ${launch?.command ?? "(not resolved)"}`,
    `Working directory: ${launch?.cwd ?? "(not resolved)"}`,
    `Exit code: ${backendExitCode ?? backendSidecar?.exitCode ?? "(none)"}`,
    `Exit signal: ${backendExitSignal ?? backendSidecar?.signalCode ?? "(none)"}`,
    ...(backendSpawnError ? [`Spawn error: ${backendSpawnError.message}`] : []),
    "",
    "Runtime diagnostics:",
    `API URL: ${process.env.AGENT_RUNTIME_API_BASE_URL ?? "(not configured)"}`,
    `Data directory: ${runtimeDataDirectory}`,
    `Checkpoint DB: ${process.env.CODING_AGENT_MEMORY_CHECKPOINT_DB ?? "(not configured)"}`,
    `Store DB: ${process.env.CODING_AGENT_MEMORY_STORE_DB ?? "(not configured)"}`,
    ...(output
      ? [
          "",
          "Last FastAPI/PyInstaller output:",
          redactRuntimeSecrets(output),
        ]
      : [
          "",
          "No stdout/stderr was captured from the sidecar before it exited.",
        ]),
    ...(diagnosticLogPath
      ? ["", `Startup diagnostic log: ${diagnosticLogPath}`]
      : []),
  ];

  return details.join("\n");
}

function configureRuntimeDataPaths() {
  mkdirSync(memoryDirectory, { recursive: true });

  // A managed backend inherits one complete, explicit layout. These assignments
  // happen before the backend child process is launched.
  process.env.AGENT_RUNTIME_DATA_DIR = runtimeDataDirectory;
  process.env.AGENT_RUNTIME_CONFIG_PATH = path.join(
    runtimeDataDirectory,
    "runtime-agent-config.json",
  );
  process.env.AGENT_RUNTIME_LOCAL_REPOSITORY_SESSION_PATH = path.join(
    runtimeDataDirectory,
    "local-repository-session.json",
  );
  process.env.GITHUB_WORKSPACE_ROOT = path.join(
    runtimeDataDirectory,
    "github-workspaces",
  );
  process.env.CODING_AGENT_MEMORY_DIR = memoryDirectory;
  process.env.CODING_AGENT_MEMORY_CHECKPOINT_DB = path.join(
    memoryDirectory,
    "checkpoints.sqlite3",
  );
  process.env.CODING_AGENT_MEMORY_STORE_DB = path.join(
    memoryDirectory,
    "store.sqlite3",
  );
  process.env.CODING_AGENT_MEMORY_EMBEDDING_CACHE_DIR = path.join(
    memoryDirectory,
    "fastembed-cache",
  );
  process.env.CODING_AGENT_MEMORY_MAINTENANCE_STATE = path.join(
    memoryDirectory,
    "maintenance.json",
  );
  process.env.CODING_AGENT_MEMORY_ENABLED ??= "true";
  process.env.CODING_AGENT_MEMORY_SETUP ??= "true";
  process.env.AGENT_RUNTIME_INITIALIZE_MEMORY_ON_STARTUP ??= "true";

  // NoDiff is a long-lived desktop process. Keep LangSmith trace uploads in
  // the background so request completion never waits on trace transport.
  process.env.LANGCHAIN_CALLBACKS_BACKGROUND = "true";
}

configureRuntimeDataPaths();

function reserveLoopbackPort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.unref();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close();
        reject(new Error("Unable to reserve a loopback port for the FastAPI sidecar."));
        return;
      }

      const { port } = address;
      server.close((error) => {
        if (error) reject(error);
        else resolve(port);
      });
    });
  });
}

async function configureRuntimeConnection() {
  const configuredPort = Number.parseInt(process.env.AGENT_RUNTIME_PORT ?? "", 10);
  const port = Number.isInteger(configuredPort) && configuredPort > 0
    ? configuredPort
    : await reserveLoopbackPort();

  process.env.AGENT_RUNTIME_HOST = "127.0.0.1";
  process.env.AGENT_RUNTIME_PORT = String(port);
  process.env.AGENT_RUNTIME_API_BASE_URL = `http://127.0.0.1:${port}`;
  process.env.AGENT_RUNTIME_API_KEY ??= randomBytes(32).toString("base64url");

  // The packaged renderer is loaded from file:// and therefore sends a null
  // Origin on cross-origin requests. Development continues to use Vite's origin.
  if (!process.env.AGENT_RUNTIME_ALLOWED_ORIGINS) {
    process.env.AGENT_RUNTIME_ALLOWED_ORIGINS = developmentServerUrl
      ? new URL(developmentServerUrl).origin
      : "null";
  }
}

function resolveSidecarLaunch(): SidecarLaunch {
  if (app.isPackaged) {
    if (process.platform !== "win32") {
      throw new Error("The packaged FastAPI sidecar is currently configured for Windows builds only.");
    }

    const sidecarDirectory = path.join(
      process.resourcesPath,
      "backend",
      "nodiff-agent-runtime",
    );
    const executable = path.join(sidecarDirectory, "nodiff-agent-runtime.exe");

    if (!existsSync(executable)) {
      throw new Error(
        `FastAPI sidecar executable was not packaged at ${executable}. ` +
          "Run the backend PyInstaller build before electron-builder.",
      );
    }

    return {
      command: executable,
      args: [],
      cwd: sidecarDirectory,
    };
  }

  return {
    command: "uv",
    args: ["run", "python", "-m", "agent_runtime.api.main"],
    cwd: backendSourceDirectory,
  };
}

function backendIsRunning() {
  return (
    backendSidecar !== null &&
    backendSidecar.exitCode === null &&
    backendSpawnError === null
  );
}

async function waitForBackendReady(timeoutMs = 45_000) {
  const baseUrl = process.env.AGENT_RUNTIME_API_BASE_URL;
  if (!baseUrl) throw new Error("FastAPI base URL was not configured.");

  const deadline = Date.now() + timeoutMs;
  let lastError: unknown = null;

  while (Date.now() < deadline) {
    if (backendSidecar && backendSidecar.exitCode !== null) {
      throw new Error(
        `FastAPI sidecar exited before becoming ready (exit code ${backendSidecar.exitCode}).`,
      );
    }

    try {
      const response = await fetch(`${baseUrl}/health`, {
        signal: AbortSignal.timeout(1_000),
      });
      if (response.ok) return;
      lastError = new Error(`Health check returned HTTP ${response.status}.`);
    } catch (error) {
      lastError = error;
    }

    await new Promise((resolve) => setTimeout(resolve, 250));
  }

  throw new Error(
    `FastAPI sidecar did not become ready within ${timeoutMs / 1000} seconds.` +
      (lastError instanceof Error ? ` ${lastError.message}` : ""),
  );
}

async function startBackendSidecar() {
  if (backendIsRunning()) return;

  const launch = resolveSidecarLaunch();
  activeSidecarLaunch = launch;
  backendStdoutTail = "";
  backendStderrTail = "";
  backendSpawnError = null;
  backendExitCode = null;
  backendExitSignal = null;

  backendSidecar = spawn(launch.command, launch.args, {
    cwd: launch.cwd,
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true,
  });

  const child = backendSidecar;
  backendClosePromise = new Promise<void>((resolve) => {
    child.once("close", () => resolve());
  });

  child.stdout.on("data", (chunk: Buffer) => {
    backendStdoutTail = appendDiagnosticTail(backendStdoutTail, chunk);
    console.log(`[FastAPI] ${chunk.toString().trimEnd()}`);
  });

  child.stderr.on("data", (chunk: Buffer) => {
    backendStderrTail = appendDiagnosticTail(backendStderrTail, chunk);
    console.error(`[FastAPI] ${chunk.toString().trimEnd()}`);
  });

  const spawnFailure = new Promise<never>((_resolve, reject) => {
    child.once("error", (error) => {
      backendSpawnError = error;
      console.error("FastAPI sidecar process error", error);
      reject(
        new Error(
          `Unable to launch the FastAPI sidecar process: ${error.message}`,
        ),
      );
    });
  });

  child.once("exit", (code, signal) => {
    backendExitCode = code;
    backendExitSignal = signal;
    console.log(
      `FastAPI sidecar exited (code=${String(code)}, signal=${String(signal)}).`,
    );
  });

  await Promise.race([waitForBackendReady(), spawnFailure]);
}

async function stopBackendSidecar() {
  const child = backendSidecar;
  if (!child || child.exitCode !== null || backendSpawnError !== null) {
    backendSidecar = null;
    return;
  }

  await new Promise<void>((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(forceKillTimer);
      resolve();
    };

    const forceKillTimer = setTimeout(() => {
      console.warn("FastAPI sidecar did not shut down gracefully; terminating it.");
      child.kill();
      finish();
    }, 7_500);

    child.once("exit", finish);

    try {
      child.stdin.write("shutdown\n");
      child.stdin.end();
    } catch (error) {
      console.error("Unable to send graceful shutdown to FastAPI sidecar", error);
      child.kill();
      finish();
    }
  });

  backendSidecar = null;
}

function existingDirectory(value: unknown): string | undefined {
  if (typeof value !== "string" || !value.trim()) return undefined;

  try {
    const candidate = path.resolve(value.trim());
    return existsSync(candidate) && statSync(candidate).isDirectory()
      ? candidate
      : undefined;
  } catch {
    return undefined;
  }
}

function registerDesktopIpc() {
  // removeHandler keeps development main-process reloads from registering the
  // same channel more than once.
  ipcMain.removeHandler("desktop:select-directory");
  ipcMain.removeHandler("desktop:api-request");
  ipcMain.removeHandler("desktop:persist-runtime-secrets");

  ipcMain.handle(
    "desktop:api-request",
    async (_event, request: DesktopApiRequest): Promise<DesktopApiResponse> => {
      const baseUrl = process.env.AGENT_RUNTIME_API_BASE_URL;
      const apiKey = process.env.AGENT_RUNTIME_API_KEY;
      if (!baseUrl || !apiKey) {
        throw new Error("The FastAPI runtime connection is not configured.");
      }

      let target: URL;
      let runtimeOrigin: string;
      try {
        target = new URL(request.url);
        runtimeOrigin = new URL(baseUrl).origin;
      } catch {
        throw new Error("Invalid FastAPI request URL.");
      }

      // The bridge is intentionally restricted to the single managed loopback
      // sidecar. A compromised renderer cannot turn this into a generic HTTP proxy.
      if (target.origin !== runtimeOrigin) {
        throw new Error("Desktop API requests may only target the managed FastAPI sidecar.");
      }

      const method = (request.method ?? "GET").toUpperCase();
      if (!["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"].includes(method)) {
        throw new Error(`Unsupported desktop API method: ${method}`);
      }

      const headers = new Headers(request.headers ?? {});
      headers.delete("host");
      headers.delete("origin");
      headers.delete("content-length");
      headers.set("x-api-key", apiKey);

      const timeoutMs = Math.min(
        Math.max(Number(request.timeoutMs ?? 300_000), 1_000),
        600_000,
      );

      const requestId = randomBytes(5).toString("hex");
      const startedAt = Date.now();
      console.log(
        `[desktop-api:${requestId}] -> ${method} ${target.pathname}${target.search} timeout=${timeoutMs}ms`,
      );

      try {
        const response = await fetch(target, {
          method,
          headers,
          body: method === "GET" || method === "HEAD" ? undefined : request.body ?? undefined,
          signal: AbortSignal.timeout(timeoutMs),
          redirect: "error",
        });

        const responseHeaders: Record<string, string> = {};
        response.headers.forEach((value, key) => {
          responseHeaders[key] = value;
        });
        const body = await response.text();
        console.log(
          `[desktop-api:${requestId}] <- ${response.status} ${method} ${target.pathname} ${Date.now() - startedAt}ms`,
        );
        if (!response.ok || Date.now() - startedAt >= 10_000) {
          logDesktopApi(`${requestId} ${method} ${target.pathname} -> ${response.status} ${Date.now() - startedAt}ms backend-request=${response.headers.get("x-request-id") ?? "none"}`);
        }

        return {
          status: response.status,
          statusText: response.statusText,
          ok: response.ok,
          headers: responseHeaders,
          body,
        };
      } catch (error) {
        logDesktopApi(`${requestId} ${method} ${target.pathname} failed after ${Date.now() - startedAt}ms: ${String(error)}`);
        console.error(
          `[desktop-api:${requestId}] !! ${method} ${target.pathname} failed after ${Date.now() - startedAt}ms`,
          error,
        );
        throw error;
      }
    },
  );

  ipcMain.handle(
    "desktop:select-directory",
    async (event, options?: DesktopDirectoryPickerOptions) => {
      const owner = BrowserWindow.fromWebContents(event.sender);
      const requestedTitle =
        typeof options?.title === "string" ? options.title.trim() : "";
      const dialogOptions: OpenDialogOptions = {
        title: requestedTitle.slice(0, 200) || "Select repository root",
        // A WSL path saved by an older build is not usable by a native Windows
        // dialog. Fall back to Documents until the user selects a Windows path.
        defaultPath:
          existingDirectory(options?.defaultPath) ?? app.getPath("documents"),
        properties: ["openDirectory"],
      };

      const result = owner
        ? await dialog.showOpenDialog(owner, dialogOptions)
        : await dialog.showOpenDialog(dialogOptions);

      if (result.canceled || result.filePaths.length === 0) return null;
      return path.normalize(result.filePaths[0]);
    },
  );

  ipcMain.handle(
  "desktop:persist-runtime-secrets",
  (_event, values: Record<string, string>) => {
    persistRuntimeSecrets(values);
    return { persisted: true };
  },
);
}

function resolveApplicationIcon() {
  return app.isPackaged
    ? path.join(process.resourcesPath, "branding", "icon.ico")
    : path.join(applicationRoot, "build", "icon.ico");
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    backgroundColor: "#090b10",
    title: "NoDiff",
    icon: resolveApplicationIcon(),
    webPreferences: {
      preload: path.join(currentDirectory, "preload.mjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  window.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: "deny" };
  });

  if (developmentServerUrl) {
    void window.loadURL(developmentServerUrl);
  } else {
    void window.loadFile(path.join(applicationRoot, "dist", "index.html"));
  }
}

app.whenReady().then(async () => {
  app.setAppUserModelId("com.kennangauthier.nodiff");
  registerDesktopIpc();

  try {
    loadPersistentRuntimeSecrets();
    await configureRuntimeConnection();
    await startBackendSidecar();
    createWindow();
  } catch (error) {
    console.error("Unable to initialize NoDiff", error);

    // "exit" can fire just before the child stdio streams finish closing.
    // Give PyInstaller/Python a brief chance to flush the final traceback so
    // the dialog contains the useful exception instead of only "exit code 1".
    if (backendClosePromise) {
      await Promise.race([
        backendClosePromise,
        new Promise((resolve) => setTimeout(resolve, 500)),
      ]);
    }

    const diagnosticLogPath = writeSidecarDiagnosticLog(error);
    const detail = formatSidecarStartupFailure(error, diagnosticLogPath);

    dialog.showMessageBoxSync({
      type: "error",
      title: "NoDiff could not start",
      message: "The local FastAPI runtime failed to initialize.",
      detail,
      buttons: ["OK"],
      defaultId: 0,
      noLink: true,
    });

    await stopBackendSidecar();
    quitAfterBackendStops = true;
    app.quit();
    return;
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("before-quit", (event) => {
  if (quitAfterBackendStops || !backendIsRunning()) return;

  // Keep Electron alive until FastAPI has completed its graceful shutdown.
  event.preventDefault();
  if (!backendShutdownPromise) {
    backendShutdownPromise = stopBackendSidecar().finally(() => {
      quitAfterBackendStops = true;
      app.quit();
    });
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

process.on("exit", () => {
  // Last-resort cleanup for abnormal process teardown; the normal path is the
  // asynchronous before-quit handler above.
  if (backendIsRunning()) backendSidecar?.kill();
});
