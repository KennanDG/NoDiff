/// <reference types="vite/client" />

interface DesktopDirectoryPickerOptions {
  title?: string;
  defaultPath?: string;
}

interface DesktopRuntimeConnection {
  apiBaseUrl: string;
  apiKey: string;
}

interface DesktopBridge {
  platform: string;
  runtime?: DesktopRuntimeConnection;

  selectDirectory?: (
    options?: DesktopDirectoryPickerOptions,
  ) => Promise<string | null>;
}

interface Window {
  desktop?: DesktopBridge;
}
