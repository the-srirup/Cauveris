import { test, expect } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../../..");
const packageRoot = path.join(root, "tests", "e2e_packages", "memory_quota");

function makeZip(): string {
  const destination = path.join(os.tmpdir(), `cauveris-browser-${Date.now()}.zip`);
  const pythonCmd = process.env.PYTHON || (process.platform === "win32" ? "powershell.exe" : "python3");
  execFileSync(
    process.platform === "win32" ? "powershell.exe" : pythonCmd,
    process.platform === "win32"
      ? ["-NoProfile", "-Command", `Compress-Archive -Path '${packageRoot}\\*' -DestinationPath '${destination}'`]
      : ["-c", "import shutil,sys; shutil.make_archive(sys.argv[1][:-4], 'zip', sys.argv[2])", destination, packageRoot],
  );
  return destination;
}

async function signIn(page: any): Promise<void> {
  await page.goto("/login");
  await page.locator("#email").fill("operator@cauveris.ai");
  await page.locator("#password").fill("Operator123456!");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/workspace/);
  await expect(page.getByRole("heading", { name: "Workspace", exact: true })).toBeVisible({ timeout: 15_000 });
}

test("real upload observes stages and exposes the verified repair", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (request) => requests.push(`${request.method()} ${request.url()}`));
  const zip = makeZip();
  try {
    await signIn(page);

    // Open upload wizard from Workspace Hub via primary CTA
    await page.getByRole("button", { name: /New Incident Investigation/i }).click();
    await expect(page).toHaveURL(/\/workspace\/new/);

    // Step 1: Attach evidence archive ZIP and continue
    await page.locator('input[type="file"]').setInputFiles(zip);
    await page.getByRole("button", { name: "Continue", exact: true }).click();

    // Step 2: Fill required incident description and continue to review
    await page.locator("#wizard-description").fill("Automated E2E memory quota incident investigation");
    await page.getByRole("button", { name: "Continue", exact: true }).click();

    // Step 3: Create & open workspace, triggering upload
    const uploadPromise = page.waitForResponse(
      (res) => res.url().includes("/incidents/upload") && res.status() === 200,
    );
    await page.getByRole("button", { name: "Create & open workspace", exact: true }).click();
    const uploadRes = await uploadPromise;
    const { incident_id: uploadedIncidentId } = await uploadRes.json();
    expect(uploadedIncidentId).toBeTruthy();

    // The loading surface settles intake and routes directly to the dashboard
    await expect(page.getByRole("button", { name: "Start", exact: true })).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: "Start", exact: true }).click();

    // Wait until the investigation pipeline completes
    await expect(
      page.getByText(/Investigation pipeline completed successfully/i).first(),
    ).toBeVisible({ timeout: 150_000 });

    await page.locator('a[href="/evidence-vault"]').click();
    await expect(page.getByText(/Artifacts Indexed|forensic evidence/i).first()).toBeVisible();
    await page.goto("/reports");
    await expect(page.getByText(/Verification|Repair|Report/i).first()).toBeVisible();

    await expect.poll(async () => {
      const repair = await page.request.get(
        `http://127.0.0.1:8000/api/v1/incidents/${uploadedIncidentId}/download-patch-package`,
      );
      return repair.status();
    }, {
      message: "Wait for verified patch package ZIP to be ready for download",
      timeout: 30_000,
      intervals: [1000, 2000],
    }).toBe(200);
    await page.screenshot({ path: "test-results/production-repair.png", fullPage: true });
    expect(requests.some((request) => request.includes("/incidents/") && request.includes("/events"))).toBe(true);
  } finally {
    fs.rmSync(zip, { force: true });
  }
});

test("browser keeps honest backend failure and unsupported responses", async ({ page }) => {
  await signIn(page);
  const health = await page.request.get("http://127.0.0.1:8000/api/v1/health");
  expect(health.ok()).toBeTruthy();
  const missing = await page.request.get("http://127.0.0.1:8000/api/v1/incidents/does-not-exist/events");
  expect([401, 404]).toContain(missing.status());
});
