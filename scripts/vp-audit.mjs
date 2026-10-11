/* Viewport audit: load the page at phone/tablet/desktop sizes, report
   horizontal overflow and screenshot each. Run: node scripts/vp-audit.mjs */
import pw from 'file:///C:/Users/hextu/node_modules/playwright/index.js';
const { chromium } = pw;

const BASE = 'http://localhost:4399/index.html';
const OUT = 'C:/Users/hextu/code-engineer-1/Pink-Diamond-repo/shots';
const VIEWPORTS = [
  ['iphone-se', 375, 667],
  ['iphone-14', 390, 844],
  ['pixel-7', 412, 915],
  ['ipad-mini', 768, 1024],
  ['ipad-air', 820, 1180],
  ['ipad-pro-landscape', 1180, 820],
  ['laptop-1280', 1280, 800],
  ['desktop-1680', 1680, 1050],
];

const browser = await chromium.launch({ executablePath: 'C:/Users/hextu/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe' });
for (const [name, width, height] of VIEWPORTS) {
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 2, isMobile: width < 800, hasTouch: width < 800 });
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.click('#intro-skip').catch(() => {});
  await page.waitForTimeout(900);
  const overflows = await page.evaluate(() => {
    const doc = document.documentElement;
    const docW = doc.scrollWidth;
    const winW = window.innerWidth;
    const bad = [];
    if (docW > winW + 1) {
      // find the widest offenders
      for (const el of document.querySelectorAll('body *')) {
        const r = el.getBoundingClientRect();
        if (r.right > winW + 4 && r.width > 24 && el.offsetParent !== null) {
          const cls = (typeof el.className === 'string' ? el.className : '').slice(0, 60);
          bad.push(`${el.tagName.toLowerCase()}.${cls} right=${Math.round(r.right)} w=${Math.round(r.width)}`);
          if (bad.length > 8) break;
        }
      }
    }
    return { docW, winW, bad };
  });
  const flag = overflows.docW > overflows.winW + 1 ? 'OVERFLOW' : 'ok';
  console.log(`[${name} ${width}x${height}] doc=${overflows.docW} win=${overflows.winW} ${flag}${errors.length ? ' JS-ERR' : ''}`);
  if (overflows.bad.length) overflows.bad.forEach(b => console.log('   · ' + b));
  if (errors.length) errors.slice(0, 3).forEach(e => console.log('   ! ' + e));
  await page.screenshot({ path: `${OUT}/vp-${name}.png`, fullPage: true });
  // agent overlay check
  await page.click('.header-cta[data-launch-agent]').catch(async () => { await page.click('.primary-button[data-launch-agent]'); });
  await page.waitForTimeout(700);
  const agentOk = await page.evaluate(() => {
    const sh = document.querySelector('.agent-shell');
    const inp = document.querySelector('#agent-input');
    if (!sh || !inp) return 'missing';
    const r = sh.getBoundingClientRect();
    const inputVisible = inp.getBoundingClientRect().width > 40;
    return `shell=${Math.round(r.width)}x${Math.round(r.height)} input=${Math.round(inp.getBoundingClientRect().width)}w ${r.right > window.innerWidth + 1 ? 'OVERFLOW' : 'ok'}`;
  });
  console.log(`   agent: ${agentOk}`);
  await page.screenshot({ path: `${OUT}/vp-${name}-agent.png` });
  await page.keyboard.press('Escape').catch(() => {});
  await page.close();
}
await browser.close();
console.log('done');
