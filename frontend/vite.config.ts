/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In sviluppo il backend di docker compose è su 127.0.0.1:8000 (non localhost: su
// Windows localhost può risolvere prima in IPv6). Il proxy evita il CORS: in
// produzione la build è servita dallo stesso processo FastAPI (ADR-0001).
const backend = process.env.ACADEMY_BACKEND ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": backend, "/health": backend },
  },
  build: {
    rolldownOptions: {
      output: {
        // Librerie in chunk propri (ADR-0009 §16): cambiano di rado, quindi restano in
        // cache del browser fra un rilascio e l'altro; le pagine sono chunk lazy (App.tsx).
        // Rolldown usa "/" negli id dei moduli anche su Windows.
        codeSplitting: {
          groups: [
            { name: "react", test: /node_modules\/(react|react-dom|scheduler|react-router)\// },
            { name: "mantine", test: /node_modules\/@mantine\// },
            { name: "librerie", test: /node_modules\// },
          ],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
    restoreMocks: true,
    // e2e/ è di Playwright (npm run e2e), su docker compose.
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
