import path from "node:path"

import { defineConfig, devices } from "@playwright/test"

// End-to-end tests drive the real UI against a real API and a throw-away seeded SQLite database.
// E2E_PYTHON: interpreter with the backend requirements installed (default: python).
// E2E_CHANNEL: use an installed browser ("chrome" / "msedge") instead of Playwright's bundled Chromium.
const API_PORT = 8100
const WEB_PORT = 3100
const backendDir = path.resolve(__dirname, "../backend")
const python = process.env.E2E_PYTHON ?? "python"
const e2eDb = path.join(backendDir, "e2e.db").replaceAll("\\", "/")

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false, // the tests share one seeded database and a cash register
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    channel: process.env.E2E_CHANNEL || undefined,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], channel: process.env.E2E_CHANNEL || undefined } }],
  webServer: [
    {
      command: `"${python}" seed.py --reset --days 3 && "${python}" -m uvicorn app.main:app --port ${API_PORT}`,
      cwd: backendDir,
      url: `http://localhost:${API_PORT}/health`,
      timeout: 240_000,
      reuseExistingServer: !process.env.CI,
      env: {
        DATABASE_URL: `sqlite:///${e2eDb}`,
        ENVIRONMENT: "development",
        CORS_ORIGINS: `http://localhost:${WEB_PORT}`,
        FRONTEND_URL: `http://localhost:${WEB_PORT}`,
        RATE_LIMIT_PER_MINUTE: "100000",
        LOGIN_RATE_LIMIT_PER_MINUTE: "100000",
        SENSITIVE_RATE_LIMIT_PER_MINUTE: "100000",
        UPLOAD_DIR: path.join(backendDir, "e2e-uploads"),
        BACKUP_DIR: path.join(backendDir, "e2e-backups"),
      },
    },
    {
      command: `npm run build && npx next start -p ${WEB_PORT}`,
      url: `http://localhost:${WEB_PORT}/login`,
      timeout: 420_000,
      reuseExistingServer: !process.env.CI,
      env: { NEXT_PUBLIC_API_URL: `http://localhost:${API_PORT}`, NEXT_PUBLIC_SHOW_DEMO_LOGINS: "false" },
    },
  ],
})
