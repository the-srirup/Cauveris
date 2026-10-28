import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const python = process.platform === "win32"
  ? path.join(root, ".venv", "Scripts", "python.exe")
  : path.join(root, ".venv", "bin", "python");

export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  fullyParallel: false,
  reporter: [["list"], ["json", { outputFile: "test-results/production-e2e.json" }]],
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    ...devices["Desktop Chrome"],
  },
  webServer: [
    {
      command: `"${python}" -m uvicorn cauveris.api.main:app --host 127.0.0.1 --port 8000`,
      cwd: root,
      port: 8000,
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        CAUVERIS_DEMO_MODE: "true",
        CAUVERIS_JOB_QUEUE_BACKEND: "memory",
        CAUVERIS_JOB_QUEUE_EMBEDDED_WORKER: "true",
        CAUVERIS_LOCAL_MODEL_ENDPOINTS: "",
        CAUVERIS_RATE_LIMIT_COMPUTE: "1000/60,5000/3600",
        CAUVERIS_RATE_LIMIT_READ: "1000/60,5000/3600",
      },
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1 --port 3000",
      cwd: here,
      port: 3000,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
