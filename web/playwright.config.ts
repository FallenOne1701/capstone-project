import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// Isolated stack: API on :8001 with its own SQLite file and no LLM / Google access, web on :3001.
const API_DIR = path.resolve(__dirname, "../api");
const E2E_DATA = path.join(API_DIR, "data", "e2e");
const PY = process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";

// The config is evaluated again in every worker; clear the DB only once, in the main process.
if (!process.env.E2E_DB_CLEARED) {
  fs.rmSync(E2E_DATA, { recursive: true, force: true });
  process.env.E2E_DB_CLEARED = "1";
}

export const API = "http://localhost:8001";
export const CONSOLE_PASSWORD = "e2e-pass-123";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3001",
    actionTimeout: 15_000,
    ...devices["Desktop Chrome"],
    launchOptions: { args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] },
    permissions: ["microphone"],
  },
  webServer: [
    {
      command: `${PY} -m uvicorn --factory app.main:create_app --port 8001`,
      cwd: API_DIR,
      url: `${API}/health`,
      timeout: 180_000,
      reuseExistingServer: false,
      env: {
        DATABASE_URL: "sqlite:///./data/e2e/e2e.db",
        USE_LLM: "0",
        CONSOLE_PASSWORD,
        E2E_SEED: "1",
        TICKET_WORKER_INLINE: "0",
        AUTO_APPROVE: "0",   // Plan 3c: a person approves on the page
        SCHEDULER_ENABLED: "0",
        CORPUS_BOOTSTRAP: "0",
        // never reach Google from tests, whatever api/.env holds
        PULSE_DOC_ID: "",
        PULSE_DRAFT_RECIPIENT: "",
        GOOGLE_REFRESH_TOKEN: "",
        GOOGLE_CLIENT_ID: "",
        GOOGLE_CLIENT_SECRET: "",
      },
    },
    {
      command: "npx next dev -p 3001",
      url: "http://localhost:3001",
      timeout: 180_000,
      reuseExistingServer: false,
      env: { NEXT_PUBLIC_API_URL: API },
    },
  ],
});
