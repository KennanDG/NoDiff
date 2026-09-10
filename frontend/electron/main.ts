import path from "node:path";
import { existsSync, mkdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  shell,
  type OpenDialogOptions,
} from "electron";

const currentDirectory = path.dirname(fileURLToPath(import.meta.url));
const applicationRoot = path.join(currentDirectory, "..");
const developmentServerUrl = process.env.VITE_DEV_SERVER_URL;
const applicationDataDirectory = path.join(app.getPath("appData"), "NoDiff");

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

type DesktopDirectoryPickerOptions = {
  title?: string;
  defaultPath?: string;
};

function configureRuntimeDataPaths() {
  mkdirSync(memoryDirectory, { recursive: true });

  // A managed backend inherits one complete, explicit layout. These assignments
  // happen before any future backend child process is launched.
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
}

configureRuntimeDataPaths();

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
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    backgroundColor: "#090b10",
    title: "Coding Agent",
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

app.whenReady().then(() => {
  registerDesktopIpc();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
