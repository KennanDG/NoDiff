import { contextBridge, ipcRenderer } from "electron";

export type DesktopDirectoryPickerOptions = {
  title?: string;
  defaultPath?: string;
};

export type DesktopRuntimeConnection = {
  apiBaseUrl: string;
  apiKey: string;
};

export type DesktopApiRequest = {
  url: string;
  method?: string;
  headers?: Record<string, string>;
  body?: string | null;
  timeoutMs?: number;
};

export type DesktopApiResponse = {
  status: number;
  statusText: string;
  ok: boolean;
  headers: Record<string, string>;
  body: string;
};

export type DesktopApi = {
  platform: NodeJS.Platform;
  runtime: DesktopRuntimeConnection;
  apiRequest: (request: DesktopApiRequest) => Promise<DesktopApiResponse>;
  selectDirectory: (options?: DesktopDirectoryPickerOptions) => Promise<string | null>;
};

const desktopApi: DesktopApi = Object.freeze({
  platform: process.platform,
  runtime: Object.freeze({
    apiBaseUrl:
      process.env.AGENT_RUNTIME_API_BASE_URL ?? "http://127.0.0.1:8765",
    apiKey: process.env.AGENT_RUNTIME_API_KEY ?? "",
  }),
  apiRequest: (request) =>
    ipcRenderer.invoke("desktop:api-request", request) as Promise<DesktopApiResponse>,
  selectDirectory: (options) =>
    ipcRenderer.invoke("desktop:select-directory", options) as Promise<string | null>,
});

contextBridge.exposeInMainWorld("desktop", desktopApi);
