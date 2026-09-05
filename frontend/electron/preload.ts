import { contextBridge, ipcRenderer } from "electron";

export type DesktopDirectoryPickerOptions = {
  title?: string;
  defaultPath?: string;
};

export type DesktopApi = {
  platform: NodeJS.Platform;
  selectDirectory: (options?: DesktopDirectoryPickerOptions) => Promise<string | null>;
};

const desktopApi: DesktopApi = Object.freeze({
  platform: process.platform,
  selectDirectory: (options) =>
    ipcRenderer.invoke("desktop:select-directory", options) as Promise<string | null>,
});

contextBridge.exposeInMainWorld("desktop", desktopApi);
