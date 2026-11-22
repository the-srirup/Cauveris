import { chromium } from "playwright";
import fs from "node:fs";

const ROUTES = process.argv[2]
  ? process.argv[2].split(",")
  : ["/", "/evidence-vault", "/patch-forge", "/holographic-reconstruction", "/reports", "/ghost-lab", "/causal-constellation", "/victory-replay", "/reality-rewind", "/settings"];

// "dark" | "light" — the app stores the chosen theme in localStorage and the
// bootstrap script in app/layout.tsx reads it before first paint.
const THEME = process.argv[3] || "dark";

const OUT = THEME === "light" ? "screenshots/light" : "screenshots/dark";
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1600, height: 1000 },
  deviceScaleFactor: 1,
});

// Seed the theme before any page script runs, so the very first paint is
// already in the requested theme and no flash is captured.
await context.addInitScript((theme) => {
  try {
    const raw = localStorage.getItem("cauveris-settings");
    const settings = raw ? JSON.parse(raw) : {};
    settings.theme = theme;
    localStorage.setItem("cauveris-settings", JSON.stringify(settings));
  } catch {}
}, THEME);

const page = await context.newPage();

const consoleErrors = [];
page.on("console", (m) => {
  if (m.type() === "error") consoleErrors.push(`[${m.location().url}] ${m.text()}`);
});
page.on("pageerror", (e) => consoleErrors.push(`[pageerror] ${e.message}`));

// Sign in first — every route is behind the auth gate.
await page.goto("http://127.0.0.1:3000/login", { waitUntil: "networkidle", timeout: 45000 });
await page.locator("#email").fill("operator@cauveris.ai");
await page.locator("#password").fill("Operator123456!");
await page.getByRole("button", { name: /sign in/i }).click();
await page.waitForURL(/\/$/, { timeout: 30000 });
await page.waitForTimeout(1500);

for (const route of ROUTES) {
  const name = route === "/" ? "root" : route.replace(/\//g, "-").replace(/^-/, "");
  try {
    await page.goto(`http://127.0.0.1:3000${route}`, {
      waitUntil: "networkidle",
      timeout: 45000,
    });
    await page.waitForTimeout(2200);
    await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: false });
    const title = await page.title();
    const h1 = await page.locator("h1").first().textContent().catch(() => null);
    const themeAttr = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    console.log(
      `OK   ${route.padEnd(28)} theme="${themeAttr}" title="${title}" h1="${(h1 || "").trim().slice(0, 60)}"`
    );
  } catch (e) {
    console.log(`FAIL ${route.padEnd(28)} ${e.message.split("\n")[0]}`);
  }
}

await browser.close();

console.log("\n=== CONSOLE ERRORS ===");
if (consoleErrors.length === 0) console.log("(none)");
else [...new Set(consoleErrors)].slice(0, 40).forEach((e) => console.log(e));
