import path from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import electron from "vite-plugin-electron/simple";

const rootDirectory = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, rootDirectory, "");
  const developmentApiBase = JSON.stringify(
    env.VITE_AI_AGENTS_API_BASE || "http://0.0.0.0:8000",
  );
  const developmentApiKey = JSON.stringify(env.VITE_AI_AGENTS_API_KEY || "");

  return {
    // App.tsx already reads these Vite environment keys throughout the renderer.
    // In the desktop app, replace them with the runtime connection that Electron
    // created before FastAPI started. A browser-only development session keeps
    // the existing .env behavior as a fallback.
    define: {
      "import.meta.env.VITE_AI_AGENTS_API_BASE":
        `(window.desktop?.runtime?.apiBaseUrl ?? ${developmentApiBase})`,
      "import.meta.env.VITE_AI_AGENTS_API_KEY":
        `(window.desktop?.runtime?.apiKey ?? ${developmentApiKey})`,
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
  };
});
