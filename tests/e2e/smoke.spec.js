const { test, expect } = require("@playwright/test");
const http = require("http");
const { promises: fs } = require("fs");

const modeFilePath = process.env.SCANEXPRESS_FAKE_SCAN_MODE_FILE;

if (!modeFilePath) {
  throw new Error("SCANEXPRESS_FAKE_SCAN_MODE_FILE must be set for e2e tests.");
}

let fakePaperlessServer;
let paperlessUploadDelayMs = 0;

test.beforeAll(async () => {
  fakePaperlessServer = http.createServer((req, res) => {
    if (req.method === "POST" && req.url === "/api/documents/post_document/") {
      req.on("data", () => {});
      req.on("end", () => {
        setTimeout(() => {
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ id: 4242 }));
        }, paperlessUploadDelayMs);
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
  paperlessUploadDelayMs = 0;
  await fs.writeFile(modeFilePath, "success", "utf-8");
});

test("loads page with idle state", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "ScanExpress" })).toBeVisible();
  const filenameInput = page.getByLabel("Filename");
  await expect(filenameInput).toBeVisible();
  await expect(filenameInput).toHaveValue(/^scan_[0-9A-Za-z]+$/);
  await expect(page.getByText("Device configuration")).toBeVisible();
  await expect(page.locator('input[name="deviceConfig"]')).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Start Scan" })).toBeVisible();
  await expect(page.locator("#statusText")).toHaveText("Status: idle");
});

test("filename input click does not auto-select full content", async ({ page }) => {
  await page.goto("/");

  const filenameInput = page.getByLabel("Filename");
  await filenameInput.click();

  const selection = await filenameInput.evaluate((element) => ({
    start: element.selectionStart,
    end: element.selectionEnd,
    length: element.value.length,
  }));
  expect(selection.start).toBe(selection.end);
  expect(selection.end).toBeLessThanOrEqual(selection.length);
});

test("filename input shows error style when empty filename is submitted", async ({ page }) => {
  await page.goto("/");

  const filenameInput = page.getByLabel("Filename");
  await filenameInput.fill("   ");
  await page.getByRole("button", { name: "Start Scan" }).click();

  await expect(filenameInput).toHaveClass(/input-error/);
  await expect(page.locator("#statusText")).toHaveText("Status: error (Filename cannot be empty)");
});

test("scan controls appear above device selection", async ({ page }) => {
  await page.goto("/");

  const scanButton = page.getByRole("button", { name: "Start Scan" });
  const deviceLegend = page.getByText("Device configuration", { exact: true });

  const scanBox = await scanButton.boundingBox();
  const deviceBox = await deviceLegend.boundingBox();

  expect(scanBox).not.toBeNull();
  expect(deviceBox).not.toBeNull();
  expect(scanBox.y).toBeLessThan(deviceBox.y);
});

test("device configuration selector shows available devices and selected details", async ({ page }) => {
  await page.goto("/");

  const fakeRadio = page.locator('input[name="deviceConfig"][value="fake"]');
  const flatbedRadio = page.locator('input[name="deviceConfig"][value="flatbed"]');
  await expect(fakeRadio).toBeChecked();
  await expect(flatbedRadio).not.toBeChecked();

  const detailsPanel = page.locator("#deviceDetailsPanel");
  await expect(detailsPanel).not.toHaveAttribute("open", "");

  await page.locator("#deviceDetailsSummary").click();
  await expect(detailsPanel).toHaveAttribute("open", "");
  await expect(page.locator("#deviceDetails")).toContainText("fake-device");
  await expect(page.locator("#deviceDetails")).toContainText("Automatic Document Feeder");

  await flatbedRadio.check();

  await expect(flatbedRadio).toBeChecked();
  await expect(page.locator("#deviceDetails")).toContainText("flatbed-device");
  await expect(page.locator("#deviceDetails")).toContainText("Flatbed");
  await expect(page.locator("#statusText")).toHaveText("Status: selected (flatbed)");
});

test("clicking Start Scan runs backend with fake scanner and fake Paperless", async ({ page }) => {
  await page.goto("/");
  const filenameInput = page.getByLabel("Filename");
  const filenameBefore = await filenameInput.inputValue();
  await page.getByRole("button", { name: "Start Scan" }).click();

  await expect(page.locator("#statusText")).toHaveText(/^Status: ok \(.+\)$/);
  await expect(page.locator("#statusStats")).toHaveText(
    /^Total: \d+s\nScan: \d+s\nPaperless: \d+s\nScan\/page: \d+s\nPaperless\/page: \d+s$/
  );
  const filenameAfter = await filenameInput.inputValue();
  expect(filenameAfter).toMatch(/^scan_[0-9A-Za-z]+$/);
  expect(filenameAfter).not.toBe(filenameBefore);
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

test("switching device while scan is running enables Start Scan for other device", async ({ page }) => {
  await fs.writeFile(modeFilePath, "slow", "utf-8");

  await page.goto("/");

  const scanButton = page.getByRole("button", { name: "Start Scan" });
  const flatbedRadio = page.locator('input[name="deviceConfig"][value="flatbed"]');

  await scanButton.click();
  await expect(scanButton).toBeDisabled();

  await flatbedRadio.check();
  await expect(flatbedRadio).toBeChecked();
  await expect(scanButton).toBeEnabled();

  await expect(page.locator("#statusText")).toHaveText(/^Status: ok \(.+\)$/);
  await expect(flatbedRadio).toBeChecked();
  await expect(scanButton).toBeEnabled();
});

test("switching to another device during upload re-enables Start Scan", async ({ page }) => {
  paperlessUploadDelayMs = 4000;

  await page.goto("/");

  const scanButton = page.getByRole("button", { name: "Start Scan" });
  const flatbedRadio = page.locator('input[name="deviceConfig"][value="flatbed"]');

  await scanButton.click();
  await expect(scanButton).toBeDisabled();
  await expect(page.locator("#statusText")).toHaveText(/Status: uploading \(.+\)/);

  await flatbedRadio.check();
  await expect(flatbedRadio).toBeChecked();
  await expect(scanButton).toBeEnabled();
  await expect(page.locator("#statusText")).toHaveText(/^Status: ok \(.+\)$/);
});

test("stale status response from previous device does not disable switched device", async ({ page }) => {
  paperlessUploadDelayMs = 9000;
  let fakeStatusCalls = 0;
  let emulateFakeBusy = false;

  await page.route("**/api/scan/status**", async (route) => {
    const url = new URL(route.request().url());
    const deviceName = url.searchParams.get("device_name");

    if (deviceName === "fake") {
      if (emulateFakeBusy) {
        fakeStatusCalls += 1;
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "ok",
          in_progress: emulateFakeBusy,
          username: "test",
          device_name: "fake",
          device_id: "fake-device",
          scanimage_device_name: "fake-device",
          device_lock_id: "fake-device",
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        in_progress: false,
        username: "test",
        device_name: "flatbed",
        device_id: "flatbed-device",
        scanimage_device_name: "flatbed-device",
        device_lock_id: "flatbed-device",
      }),
    });
  });

  await page.goto("/");

  const scanButton = page.getByRole("button", { name: "Start Scan" });
  const flatbedRadio = page.locator('input[name="deviceConfig"][value="flatbed"]');

  await scanButton.click();
  await expect(page.locator("#statusText")).toHaveText(/Status: uploading \(.+\)/);
  fakeStatusCalls = 0;
  emulateFakeBusy = true;
  await expect.poll(() => fakeStatusCalls).toBeGreaterThan(0);

  await flatbedRadio.check();
  await expect(flatbedRadio).toBeChecked();
  await expect(scanButton).toBeEnabled();

  await page.waitForTimeout(2500);
  await expect(scanButton).toBeEnabled();
});

test("recent uploads shows task polling transition and success document link", async ({ page }) => {
  let pollCount = 0;

  await page.route("**/api/scan/stream", async (route) => {
    const body =
      '{"status":"ok","message":"Scan uploaded to Paperless-ngx. pages=1","paperless_task_id":"task-1","device_name":"flatbed","complete":true}\n';
    await route.fulfill({
      status: 200,
      contentType: "application/x-ndjson",
      body,
    });
  });

  await page.route("**/api/paperless/tasks/task-1", async (route) => {
    pollCount += 1;
    if (pollCount < 2) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "ok",
          task_id: "task-1",
          task_status: "PENDING",
          related_document: null,
          result: null,
          date_done: null,
          task_file_name: "Offer.pdf",
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        task_id: "task-1",
        task_status: "SUCCESS",
        related_document: "21",
        result: "Success. New document id 21 created",
        date_done: "2026-02-24T14:33:09.254628+01:00",
        task_file_name: "Offer.pdf",
      }),
    });
  });

  await page.goto("/");
  await page.locator('input[name="deviceConfig"][value="flatbed"]').check();
  await page.getByRole("button", { name: "Start Scan" }).click();

  await expect(page.getByRole("heading", { name: "Recent uploads" })).toBeVisible();
  await expect(page.locator("#recentUploadsBody tr").first()).toContainText("SUCCESS");
  await expect(page.locator("#recentUploadsBody tr").first()).toContainText("flatbed");

  const successLink = page.locator("#recentUploadsBody tr a").first();
  await expect(successLink).toHaveAttribute("href", "http://127.0.0.1:18089/documents/21");
  await expect(successLink).toHaveAttribute("target", "_blank");
});

test("recent uploads records permanent upload timeout as failure", async ({ page }) => {
  await page.route("**/api/scan/stream", async (route) => {
    const body = [
      JSON.stringify({
        status: "uploading",
        message: "Uploading 1 page(s) to Paperless-ngx...",
        page_count: 1,
        paperless_timeout_seconds: 30,
      }),
      JSON.stringify({
        status: "error",
        message: "Paperless upload request failed: HTTPSConnectionPool(host='paperless.cloud.zonny.de', port=43443): Read timed out",
        device_name: "flatbed",
        complete: true,
      }),
    ].join("\n");

    await route.fulfill({
      status: 200,
      contentType: "application/x-ndjson",
      body: `${body}\n`,
    });
  });

  await page.goto("/");
  await page.locator('input[name="deviceConfig"][value="flatbed"]').check();
  await page.getByRole("button", { name: "Start Scan" }).click();

  const firstRow = page.locator("#recentUploadsBody tr").first();
  await expect(firstRow).toContainText("FAILURE");
  await expect(firstRow).toContainText("Read timed out");
  await expect(firstRow).toContainText("flatbed");
  await expect(firstRow.locator("a")).toHaveCount(0);
});

test("recent uploads keeps max 10 entries in newest-first order", async ({ page }) => {
  let sequence = 0;

  await page.route("**/api/scan/stream", async (route) => {
    sequence += 1;
    const taskId = `task-${sequence}`;
    const body = JSON.stringify({
      status: "ok",
      message: `Scan uploaded to Paperless-ngx. pages=1 ${taskId}`,
      paperless_task_id: taskId,
      complete: true,
    });
    await route.fulfill({
      status: 200,
      contentType: "application/x-ndjson",
      body: `${body}\n`,
    });
  });

  await page.route("**/api/paperless/tasks/*", async (route) => {
    const taskId = route.request().url().split("/").pop();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        task_id: taskId,
        task_status: "SUCCESS",
        related_document: null,
        result: "done",
        date_done: "2026-02-24T14:33:09.254628+01:00",
        task_file_name: `${taskId}.pdf`,
      }),
    });
  });

  await page.goto("/");

  const scanButton = page.getByRole("button", { name: "Start Scan" });
  for (let index = 0; index < 11; index += 1) {
    await scanButton.click();
    await expect(page.locator("#statusText")).toHaveText(/^Status: ok \(.+\)$/);
  }

  const entries = page.locator("#recentUploadsBody tr");
  await expect(entries).toHaveCount(10);
  await expect(entries.first()).toContainText("task-11");
  await expect(entries.last()).toContainText("task-2");
});
