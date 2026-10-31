export default async function run(page) {
  const out = { steps: [], consoleErrors: [], failedRequests: [] };
  page.on('console', (m) => { if (m.type() === 'error') out.consoleErrors.push(m.text()); });
  page.on('pageerror', (e) => out.consoleErrors.push('PAGEERROR: ' + e.message));
  page.on('requestfailed', (r) => out.failedRequests.push(r.url() + ' :: ' + (r.failure()?.errorText || '')));
  page.on('response', (r) => { if (r.status() >= 400) out.failedRequests.push(r.url() + ' :: HTTP ' + r.status()); });

  const wait = (ms) => page.waitForTimeout(ms);

  // 1. root -> expect redirect to /login
  await page.goto('http://localhost:3000/', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await wait(2500);
  out.steps.push({ step: 'root', url: page.url(), title: await page.title() });

  // 2. login
  const snap = await page.screenshot ? null : null;
  // find inputs by role/name
  const email = page.locator('input[type="email"], input[name="email"], input[autocomplete="email"]').first();
  const pass = page.locator('input[type="password"]').first();
  if (await email.count()) {
    await email.fill('demo@cauveris.local');
    await pass.fill('demo123456');
    const btn = page.locator('button[type="submit"], button:has-text("Sign in"), button:has-text("Log in"), button:has-text("Login")').first();
    await btn.click();
    await wait(4000);
  }
  out.steps.push({ step: 'after-login', url: page.url(), title: await page.title() });

  // helper to gather a page's state
  async function inspect(url, waitMs, label) {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await wait(waitMs);
    const info = await page.evaluate(() => {
      const text = document.body.innerText.slice(0, 1500);
      const svgs = [...document.querySelectorAll('svg')].map(s => ({
        circles: s.querySelectorAll('circle').length,
        lines: s.querySelectorAll('line').length,
        rects: s.querySelectorAll('rect').length,
        w: s.getBoundingClientRect().width, h: s.getBoundingClientRect().height,
      }));
      const canvas = document.querySelectorAll('canvas').length;
      return { url: location.href, title: document.title, bodyChars: document.body.innerText.length, text, svgs, canvas };
    });
    out.steps.push({ step: label, ...info });
    // screenshot
    const path = `E:/Document/Research/Cauveris/cauveris/.scratch/shot_${label.replace(/[^a-z0-9]+/gi, '_')}.png`;
    await page.screenshot({ path, fullPage: false });
    return info;
  }

  await inspect('http://localhost:3000/', 6000, 'home');

  // Try to activate newest INC- incident: look for a select or buttons containing INC-
  const incSel = await page.evaluate(() => {
    const els = [...document.querySelectorAll('button, [role=option], [role=button], select option, a')].map(e => e.textContent || '').filter(t => /INC-[0-9A-F]{8}/.test(t));
    return els.slice(0, 10);
  });
  out.incidentButtons = incSel;

  await inspect('http://localhost:3000/causal-constellation', 9000, 'constellation');
  await inspect('http://localhost:3000/reports', 7000, 'reports');
  await inspect('http://localhost:3000/evidence-vault', 7000, 'evidence');
  await inspect('http://localhost:3000/ghost-lab', 7000, 'ghostlab');
  await inspect('http://localhost:3000/settings', 5000, 'settings');
  await inspect('http://localhost:3000/holographic-reconstruction', 7000, 'holographic');
  await inspect('http://localhost:3000/reality-rewind', 7000, 'rewind');
  await inspect('http://localhost:3000/victory-replay', 7000, 'victory');
  await inspect('http://localhost:3000/patch-forge', 7000, 'patchforge');

  return out;
}
