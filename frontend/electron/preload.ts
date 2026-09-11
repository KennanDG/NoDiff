import { contextBridge, ipcRenderer } from "electron";

export type DesktopDirectoryPickerOptions = {
  title?: string;
  defaultPath?: string;
};

export type DesktopRuntimeConnection = {
  apiBaseUrl: string;
  apiKey: string;
};

export type DesktopApi = {
  platform: NodeJS.Platform;
  runtime: DesktopRuntimeConnection;
  selectDirectory: (options?: DesktopDirectoryPickerOptions) => Promise<string | null>;
};

const desktopApi: DesktopApi = Object.freeze({
  platform: process.platform,
  runtime: Object.freeze({
    apiBaseUrl:
      process.env.AGENT_RUNTIME_API_BASE_URL ?? "http://127.0.0.1:8765",
    apiKey: process.env.AGENT_RUNTIME_API_KEY ?? "",
  }),
  selectDirectory: (options) =>
    ipcRenderer.invoke("desktop:select-directory", options) as Promise<string | null>,
});

contextBridge.exposeInMainWorld("desktop", desktopApi);
