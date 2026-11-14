import { defineConfig, devices } from "@playwright/test";

// End-to-end su docker compose (ADR-0009 §14): la build servita da FastAPI su :8000 e il
// login vero su Keycloak. localhost, non 127.0.0.1: è l'origine registrata nel client
// academy-web e l'emittente dei token.
const app = process.env.E2E_URL ?? "http://localhost:8000";

export default defineConfig({
  testDir: "e2e",
  // Un solo worker: i test condividono gli utenti di prova e il Keycloak di sviluppo, e
  // ogni test fa più login (ciascuno qualche secondo).
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: app,
    locale: "it-IT",
    timezoneId: "Europe/Rome",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
