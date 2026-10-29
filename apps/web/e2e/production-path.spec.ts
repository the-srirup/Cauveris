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
  execFileSync(
    process.platform === "win32" ? "powershell.exe" : "python",
    process.platform === "win32"
      ? ["-NoProfile", "-Command", `Compress-Archive -Path '${packageRoot}\\*' -DestinationPath '${destination}'`]
      : ["-c", "import shutil,sys; shutil.make_archive(sys.argv[1][:-4], 'zip', sys.argv[2])", destination, packageRoot],
  );
  return destination;
}

async function signIn(page: any): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill("operator@cauveris.ai");
  await page.getByLabel("Password").fill("Operator123456!");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/$/);
}

test("real upload observes stages and exposes the verified repair", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (request) => requests.push(`${request.method()} ${request.url()}`));
  const zip = makeZip();
  try {
    await signIn(page);
    await page.getByRole("button", { name: "Upload incident package" }).click();
    await page.locator('input[type="file"]').setInputFiles(zip);
    await expect(page.getByText(/Incident uploaded/i)).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "Start Investigation" }).click();
    await expect(page.getByText("SUCCESS").first()).toBeVisible({ timeout: 150_000 });
    await page.getByRole("link", { name: "evidence vault", exact: true }).click();
    await expect(page.getByText(/Artifact Explorer/i)).toBeVisible();
    await page.goto("/reports");
    await expect(page.getByText(/Verification|Repair|Report/i).first()).toBeVisible();
    const incidents = await page.request.get("http://127.0.0.1:8000/api/v1/incidents");
    const incident = (await incidents.json()).incidents.find((item: any) => !item.is_demonstration);
    expect(incident).toBeTruthy();
    const repair = await page.request.get(`http://127.0.0.1:8000/api/v1/incidents/${incident.id}/download-patch-package`);
    expect(repair.ok()).toBeTruthy();
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
  expect(missing.status()).toBe(401);
});
