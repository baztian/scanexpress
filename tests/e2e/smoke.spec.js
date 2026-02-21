const { test, expect } = require("@playwright/test");

test("loads page with idle state", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "ScanExpress" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Start Scan" })).toBeVisible();
  await expect(page.locator("#statusText")).toHaveText("Status: idle");
});

test("clicking Start Scan shows not_implemented backend response", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Start Scan" }).click();

  await expect(page.locator("#statusText")).toHaveText(
    "Status: not_implemented (Scan trigger will be implemented next.)",
  );
});

test("shows mocked success response", async ({ page }) => {
  await page.route("**/api/scan", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        message: "Mock scan completed",
      }),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Start Scan" }).click();

  await expect(page.locator("#statusText")).toHaveText(
    "Status: ok (Mock scan completed)",
  );
});
