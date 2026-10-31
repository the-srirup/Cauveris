import { chromium } from 'playwright';

const OUT = { steps: [], consoleErrors: [], failedRequests: [] };
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1500, height: 950 } });
page.on('console', (m) => { if (m.type() === 'error') OUT.consoleErrors.push(m.text().slice(0, 500)); });
page.on('pageerror', (e) => OUT.consoleErrors.push('PAGEERROR: ' + String(e.message).slice(0, 500)));
page.on('requestfailed', (r) => OUT.failedRequests.push(r.url() + ' :: ' + (r.failure()?.errorText || '')));
page.on('response', (r) => { if (r.status() >= 400) OUT.failedRequests.push(r.url() + ' :: HTTP ' + r.status()); });

const wait = (ms) => page.waitForTimeout(ms);

async function inspect(url, waitMs, label) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 40000 });
  await wait(waitMs);
  const info = await page.evaluate(() => {
    const svgs = [...document.querySelectorAll('svg')].map((s) => ({
      circles: s.querySelectorAll('circle').length,
      lines: s.querySelectorAll('line').length,
      edges: s.querySelectorAll('path').length,
      w: Math.round(s.getBoundingClientRect().width), h: Math.round(s.getBoundingClientRect().height),
    }));
    return {
      url: location.href, title: document.title, bodyChars: document.body.innerText.length,
      text: document.body.innerText.slice(0, 1200), svgs, canvas: document.querySelectorAll('canvas').length,
    };
  });
  OUT.steps.push({ step: label, ...info });
  await page.screenshot({ path: `E:/Document/Research/Cauveris/cauveris/.scratch/shot_${label}.png` });
  return info;
}

// root
await page.goto('http://localhost:3000/', { waitUntil: 'domcontentloaded', timeout: 40000 });
await wait(3000);
OUT.steps.push({ step: 'root-redirect', url: page.url(), title: await page.title() });

// login
const email = page.locator('input[type="email"], input[name="email"], input[autocomplete="email"]').first();
const pass = page.locator('input[type="password"]').first();
if (await email.count()) {
  await email.fill('demo@cauveris.local');
  await pass.fill('demo123456');
  const btn = page.locator('button[type="submit"]').first();
  await btn.click();
  await wait(5000);
} else {
  OUT.loginError = 'no email input found';
}
OUT.steps.push({ step: 'after-login', url: page.url(), title: await page.title() });

// capture incident selector options on home
const home = await inspect('http://localhost:3000/', 7000, 'home');
OUT.incidentText = await page.evaluate(() => {
  return [...document.querySelectorAll('button, select option, [role="option"], a')]
    .map((e) => (e.textContent || '').trim())
    .filter((t) => /INC-[0-9A-F]{8}|CAU-\d+|DEMO-/.test(t)).slice(0, 20);
});

await inspect('http://localhost:3000/causal-constellation', 10000, 'constellation');
await inspect('http://localhost:3000/reports', 8000, 'reports');
await inspect('http://localhost:3000/evidence-vault', 8000, 'evidence');
await inspect('http://localhost:3000/ghost-lab', 8000, 'ghostlab');
await inspect('http://localhost:3000/settings', 6000, 'settings');
await inspect('http://localhost:3000/holographic-reconstruction', 8000, 'holographic');
await inspect('http://localhost:3000/reality-rewind', 8000, 'rewind');
await inspect('http://localhost:3000/victory-replay', 8000, 'victory');
await inspect('http://localhost:3000/patch-forge', 8000, 'patchforge');

await browser.close();
console.log(JSON.stringify(OUT, null, 1));
