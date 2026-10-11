/* Mobile/tablet functional test: drawer, model menu, no overflow, modals fit. */
import pw from 'file:///C:/Users/hextu/node_modules/playwright/index.js';
const { chromium } = pw;

const BASE = 'http://localhost:4399/index.html';
const OUT = 'C:/Users/hextu/head-coding-agent/shots';
const fails = [], oks = [];
const check = (n, c, e = '') => (c ? oks : fails).push(n + (e ? ' — ' + e : ''));

const browser = await chromium.launch({ executablePath: 'C:/Users/hextu/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe' });
for (const [name, w, h] of [['phone', 390, 844], ['tablet', 768, 1024]]) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.click('#intro-skip').catch(() => {});
  await page.waitForTimeout(800);

  check(`${name}: no horizontal overflow`, await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
    `${await page.evaluate(() => document.documentElement.scrollWidth)} vs ${w}`);

  // hamburger nav menu opens and links are visible
  await page.click('.menu-button').catch(() => {});
  check(`${name}: nav menu opens`, await page.locator('.main-nav a').first().isVisible());
  await page.click('.main-nav a').catch(() => {});

  // agent opens full-width, drawer works
  await page.click('.header-cta[data-launch-agent]');
  await page.waitForTimeout(600);
  check(`${name}: agent input visible`, await page.locator('#agent-input').isVisible());
  check(`${name}: agent fits width`, await page.evaluate(() => {
    const r = document.querySelector('.agent-shell').getBoundingClientRect();
    return r.left >= -1 && r.right <= window.innerWidth + 1;
  }));
  check(`${name}: drawer toggle visible`, await page.locator('#agent-menu-toggle').isVisible());
  await page.click('#agent-menu-toggle');
  await page.waitForTimeout(400);
  check(`${name}: sidebar drawer opens`, await page.locator('.agent-balance').isVisible());
  await page.screenshot({ path: `${OUT}/${name}-drawer.png` });
  await page.click('#agent-model');
  await page.waitForTimeout(500);
  const menuVisible = await page.locator('.model-menu').isVisible();
  check(`${name}: model menu opens in drawer`, menuVisible);
  const menuFits = await page.evaluate(() => {
    const m = document.querySelector('.model-menu').getBoundingClientRect();
    return m.left >= -1 && m.right <= window.innerWidth + 1;
  });
  check(`${name}: model menu fits screen`, menuFits);
  await page.screenshot({ path: `${OUT}/${name}-modelmenu.png` });
  await page.click('#agent-model');   // close the model menu first
  await page.waitForTimeout(400);
  await page.locator('.agent-nav-item').first().click();
  await page.waitForTimeout(300);
  check(`${name}: drawer closes on nav pick`, !(await page.locator('.agent-balance').isVisible().catch(() => false)));

  // auth modal fits
  await page.click('.agent-close');
  await page.waitForTimeout(400);
  await page.click('[data-open-auth="signin"]').catch(() => {});
  await page.waitForTimeout(400);
  check(`${name}: auth modal fits`, await page.evaluate(() => {
    const c = document.querySelector('#auth-modal .modal-card').getBoundingClientRect();
    return c.left >= -1 && c.right <= window.innerWidth + 1 && c.top >= -1;
  }));
  check(`${name}: no JS errors`, errors.length === 0, errors.join(' | ').slice(0, 120));
  await page.close();
}

// desktop: plan grid still 5 across and no overflow at 1280
const page = await browser.newPage({ viewport: { width: 1680, height: 1050 } });
await page.goto(BASE, { waitUntil: 'networkidle' });
await page.click('#intro-skip').catch(() => {});
await page.waitForTimeout(600);
const cols = await page.evaluate(() => getComputedStyle(document.querySelector('.plan-grid')).gridTemplateColumns.split(' ').length);
check('desktop: plan grid keeps 5 columns', cols === 5, 'got ' + cols);
await page.close();
const p2 = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await p2.goto(BASE, { waitUntil: 'networkidle' });
await p2.click('#intro-skip').catch(() => {});
await p2.waitForTimeout(600);
check('1280px: no horizontal overflow', await p2.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  `${await p2.evaluate(() => document.documentElement.scrollWidth)}`);
await p2.close();

await browser.close();
console.log('PASS: ' + oks.length);
oks.forEach(o => console.log('  ✓ ' + o));
if (fails.length) { console.log('FAIL: ' + fails.length); fails.forEach(f => console.log('  ✗ ' + f)); process.exit(1); }
