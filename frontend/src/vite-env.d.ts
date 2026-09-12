/// <reference types="vite/client" />

interface DesktopDirectoryPickerOptions {
  title?: string;
  defaultPath?: string;
}

interface DesktopRuntimeConnection {
  apiBaseUrl: string;
  apiKey: string;
}

interface DesktopApiRequest {
  url: string;
  method?: string;
  headers?: Record<string, string>;
  body?: string | null;
  timeoutMs?: number;
}

interface DesktopApiResponse {
  status: number;
  statusText: string;
  ok: boolean;
  headers: Record<string, string>;
  body: string;
}

interface DesktopBridge {
  platform: string;
  runtime?: DesktopRuntimeConnection;
  apiRequest?: (request: DesktopApiRequest) => Promise<DesktopApiResponse>;

  selectDirectory?: (
    options?: DesktopDirectoryPickerOptions,
  ) => Promise<string | null>;
}

interface Window {
  desktop?: DesktopBridge;
}
