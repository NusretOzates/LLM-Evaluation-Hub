import { defineConfig } from "@playwright/test";

const apiPort = process.env.WORKBENCH_TEST_API_PORT ?? "8000";
const webPort = process.env.WORKBENCH_TEST_WEB_PORT ?? "5173";
const apiUrl = `http://127.0.0.1:${apiPort}`;
const webUrl = `http://127.0.0.1:${webPort}`;
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  use: { baseURL: webUrl, trace: "retain-on-failure" },
  webServer: [
    {
      command: "cd .. && uv run python scripts/serve_test_catalog.py",
      url: `${apiUrl}/datasets`,
      reuseExistingServer: false,
      env: { WORKBENCH_TEST_API_PORT: apiPort },
    },
    {
      command: `npm run preview -- --port ${webPort} --strictPort`,
      url: webUrl,
      reuseExistingServer: false,
      env: { WORKBENCH_TEST_API: apiUrl },
    },
  ],
});
