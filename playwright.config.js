const { defineConfig } = require("@playwright/test");

const fakeScanModeFile = "/tmp/scanexpress-fake-scan-mode.txt";
process.env.SCANEXPRESS_FAKE_SCAN_MODE_FILE = fakeScanModeFile;

module.exports = defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  use: {
    baseURL: "http://127.0.0.1:8000",
    headless: true,
  },
  webServer: {
    command: ".venv/bin/python app.py",
    url: "http://127.0.0.1:8000",
    reuseExistingServer: true,
    timeout: 60_000,
    env: {
      SCANEXPRESS_SCAN_COMMAND: ".venv/bin/python scripts/fake_scan_wrapper.py",
      SCANEXPRESS_FAKE_SCAN_MODE_FILE: fakeScanModeFile,
      SCANEXPRESS_PAPERLESS_BASE_URL: "http://127.0.0.1:18089",
      SCANEXPRESS_PAPERLESS_API_TOKEN: "test-token",
    },
  },
});
