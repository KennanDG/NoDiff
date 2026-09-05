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

type DesktopDirectoryPickerOptions = {
  title?: string;
  defaultPath?: string;
};

function configureRuntimeDataPaths() {
  const runtimeDataDirectory = app.getPath("userData");
  const memoryDirectory = path.join(runtimeDataDirectory, "memory");

  mkdirSync(memoryDirectory, { recursive: true });

  // A managed backend inherits these paths. The defaults keep all mutable state
  // outside read-only application resources after an NSIS, DMG, or AppImage install.
  process.env.AGENT_RUNTIME_DATA_DIR ??= runtimeDataDirectory;
  process.env.CODING_AGENT_MEMORY_DIR ??= memoryDirectory;
  process.env.CODING_AGENT_MEMORY_ENABLED ??= "true";
  process.env.CODING_AGENT_MEMORY_SETUP ??= "true";
  process.env.AGENT_RUNTIME_INITIALIZE_MEMORY_ON_STARTUP ??= "true";
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
  configureRuntimeDataPaths();
  registerDesktopIpc();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
