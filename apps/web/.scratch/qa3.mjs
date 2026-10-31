import { chromium } from 'playwright';
const OUT = { steps: [], errors: [], failed: [] };
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1500, height: 950 } });
page.on('console', (m) => { if (m.type() === 'error') OUT.errors.push(m.text().slice(0,300)); });
page.on('pageerror', (e) => OUT.errors.push('PAGEERROR: ' + String(e.message).slice(0,300)));
page.on('response', (r) => { if (r.status() >= 400) OUT.failed.push(r.url() + ' :: ' + r.status()); });
const wait = (ms) => page.waitForTimeout(ms);

// login
await page.goto('http://localhost:3000/login', { waitUntil: 'domcontentloaded' });
await wait(2500);
const email = page.locator('input[type="email"], input[name="email"]').first();
const pass = page.locator('input[type="password"]').first();
await email.fill('demo@cauveris.local');
await pass.fill('demo123456');
await page.locator('button[type="submit"]').first().click();
await wait(5000);
OUT.afterLogin = page.url();

// set active incident in localStorage then load constellation
const IID = 'INC-60F368BD';
await page.evaluate((id) => { localStorage.setItem('cauveris_active_incident_id', id); }, IID);
await page.goto('http://localhost:3000/causal-constellation', { waitUntil: 'domcontentloaded' });
await wait(11000);
const c = await page.evaluate(() => {
  const svgs = [...document.querySelectorAll('svg')].map((s) => ({
    circles: s.querySelectorAll('circle').length,
    lines: s.querySelectorAll('line').length,
    w: Math.round(s.getBoundingClientRect().width), h: Math.round(s.getBoundingClientRect().height),
  }));
  const big = svgs.filter((s) => s.w > 200);
  return { svgs: big, allCount: svgs.length, text: document.body.innerText.slice(0, 1000), url: location.href };
});
OUT.constellation = c;
await page.screenshot({ path: 'E:/Document/Research/Cauveris/cauveris/.scratch/shot_constellation_sel.png' });

// Also check home with incident selected
await page.goto('http://localhost:3000/', { waitUntil: 'domcontentloaded' });
await wait(8000);
OUT.home = await page.evaluate(() => ({
  text: document.body.innerText.slice(0, 1400),
  // detect any auto reconstruct network call already happened: check localStorage flags
  storedIncident: localStorage.getItem('cauveris_active_incident_id'),
}));
await page.screenshot({ path: 'E:/Document/Research/Cauveris/cauveris/.scratch/shot_home_sel.png' });

await browser.close();
console.log(JSON.stringify(OUT, null, 1));
