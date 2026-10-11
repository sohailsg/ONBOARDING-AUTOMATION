import { defineConfig, devices } from "@playwright/test";
import { existsSync } from "node:fs";

// Prefer system Chrome where installed (CI/offline); otherwise fall back to
// the bundled Playwright chromium so `test:e2e` works on fresh machines.
const SYSTEM_CHROME = "/usr/bin/google-chrome";

export default defineConfig({
  testDir: "./tests/e2e",
  use: { baseURL: "http://localhost:3100", trace: "on-first-retry" },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(existsSync(SYSTEM_CHROME)
          ? { launchOptions: { executablePath: SYSTEM_CHROME } }
          : {}),
      },
    },
  ],
  webServer: {
    command: "npm run dev -- --port 3100",
    port: 3100,
    reuseExistingServer: true,
    // Mocked backend from tests/fixtures until staging API is up (06 §3: mock-first)
    env: { NEXT_PUBLIC_USE_MSW: "1", NEXT_PUBLIC_API_URL: "http://localhost:8000" },
  },
});
