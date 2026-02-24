const { test, expect } = require("@playwright/test");
const http = require("http");
const { promises: fs } = require("fs");

const modeFilePath = process.env.SCANEXPRESS_FAKE_SCAN_MODE_FILE;

if (!modeFilePath) {
  throw new Error("SCANEXPRESS_FAKE_SCAN_MODE_FILE must be set for e2e tests.");
}

let fakePaperlessServer;

test.beforeAll(async () => {
  fakePaperlessServer = http.createServer((req, res) => {
    if (req.method === "POST" && req.url === "/api/documents/post_document/") {
      req.on("data", () => {});
      req.on("end", () => {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ id: 4242 }));
      });
      return;
    }

    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ detail: "not found" }));
  });

  await new Promise((resolve, reject) => {
    fakePaperlessServer.once("error", reject);
    fakePaperlessServer.listen(18089, "127.0.0.1", resolve);
  });
});

test.afterAll(async () => {
  if (!fakePaperlessServer) return;

  await new Promise((resolve, reject) => {
    fakePaperlessServer.close((error) => {
      if (error) {
        reject(error);
        return;
      }
      resolve();
    });
  });
});

test.beforeEach(async () => {
  await fs.writeFile(modeFilePath, "success", "utf-8");
});

test("loads page with idle state", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "ScanExpress" })).toBeVisible();
  await expect(page.getByLabel("Device configuration")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start Scan" })).toBeVisible();
  await expect(page.locator("#statusText")).toHaveText("Status: idle");
});

test("device configuration selector shows available devices and selected details", async ({ page }) => {
  await page.goto("/");

  const selector = page.getByLabel("Device configuration");
  await expect(selector).toHaveValue("fake");
  await expect(selector.locator("option")).toHaveCount(2);
  await expect(page.locator("#deviceDetails")).toContainText("fake-device");
  await expect(page.locator("#deviceDetails")).toContainText("Automatic Document Feeder");

  await selector.selectOption("flatbed");

  await expect(selector).toHaveValue("flatbed");
  await expect(page.locator("#deviceDetails")).toContainText("flatbed-device");
  await expect(page.locator("#deviceDetails")).toContainText("Flatbed");
  await expect(page.locator("#statusText")).toHaveText("Status: selected (flatbed)");
});

test("clicking Start Scan runs backend with fake scanner and fake Paperless", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Start Scan" }).click();

  await expect(page.locator("#statusText")).toHaveText(/^Status: ok \(.+\)$/);
  await expect(page.locator("#statusStats")).toHaveText(
    /^Total: \d+s\nScan: \d+s\nPaperless: \d+s\nScan\/page: \d+s\nPaperless\/page: \d+s$/
  );
});

test("clicking Start Scan surfaces backend error when fake scanner fails", async ({ page }) => {
  await fs.writeFile(modeFilePath, "fail", "utf-8");

  await page.goto("/");
  await page.getByRole("button", { name: "Start Scan" }).click();

  await expect(page.locator("#statusText")).toHaveText(/^Status: error \(.+\)$/);
});

test("clicking Start Scan preserves multipage TIFF as multipage PDF", async ({ page }) => {
  await fs.writeFile(modeFilePath, "adf", "utf-8");

  await page.goto("/");
  await page.getByRole("button", { name: "Start Scan" }).click();

  await expect(page.locator("#statusText")).toHaveText(/Status: ok \(.+pages=3.+\)/);
});

test("reload while busy keeps Start Scan disabled", async ({ page }) => {
  await page.route("**/api/scan/status**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        in_progress: true,
        username: "test",
        device_name: "fake",
        device_id: "fake-device",
        scanimage_device_name: "fake-device",
        device_lock_id: "fake-device",
      }),
    });
  });

  await page.goto("/");

  const scanButton = page.getByRole("button", { name: "Start Scan" });
  await expect(scanButton).toBeDisabled();

  await page.reload();
  await expect(scanButton).toBeDisabled();
});

test("switching device while scan is running keeps stream and re-enables button when done", async ({ page }) => {
  await fs.writeFile(modeFilePath, "slow", "utf-8");

  await page.goto("/");

  const scanButton = page.getByRole("button", { name: "Start Scan" });
  const selector = page.getByLabel("Device configuration");

  await scanButton.click();
  await expect(scanButton).toBeDisabled();

  await selector.selectOption("flatbed");
  await expect(selector).toHaveValue("flatbed");
  await expect(scanButton).toBeDisabled();

  await expect(page.locator("#statusText")).toHaveText(/^Status: ok \(.+\)$/);
  await expect(selector).toHaveValue("flatbed");
  await expect(scanButton).toBeEnabled();
});
