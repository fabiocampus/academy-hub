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
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
    restoreMocks: true,
  },
});
