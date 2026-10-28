import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  use: { baseURL: "http://127.0.0.1:5173", trace: "retain-on-failure" },
  webServer: [
    {
      command: "cd .. && uv run python scripts/serve_test_catalog.py",
      url: "http://127.0.0.1:8000/datasets",
      reuseExistingServer: false,
    },
    {
      command: "npm run preview -- --port 5173 --strictPort",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: false,
    },
  ],
});
