import path from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import electron from "vite-plugin-electron/simple";

const rootDirectory = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  // App.tsx already reads these Vite environment keys throughout the renderer.
  // Replace them with the runtime connection Electron creates before FastAPI
  // starts. Vite/esbuild requires define replacements to be literals or simple
  // identifier/property chains, so keep these as direct property accesses.
  define: {
    "import.meta.env.VITE_AI_AGENTS_API_BASE":
      "window.desktop.runtime.apiBaseUrl",
    "import.meta.env.VITE_AI_AGENTS_API_KEY":
      "window.desktop.runtime.apiKey",
  },
  plugins: [
    react(),
    tailwindcss(),
    electron({
      main: {
        entry: "electron/main.ts",
      },
      preload: {
        input: path.join(rootDirectory, "electron/preload.ts"),
      },
    }),
  ],
});
