import pw from 'file:///C:/Users/hextu/node_modules/playwright/index.js';
const { chromium } = pw;
const BASE = 'https://pink-diamond-eight.vercel.app';
const browser = await chromium.launch({ executablePath: 'C:/Users/hextu/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe' });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
page.setDefaultTimeout(20000);
await page.goto(BASE, { waitUntil: 'networkidle' });
await page.click('#intro-skip').catch(() => {});
const email = 'e2e' + Date.now() + '@example.com';
await page.click('.text-button[data-open-auth="signin"]');
await page.waitForTimeout(400);
await page.click('#modal-switch-button');
await page.fill('#auth-form input[name="email"]', email);
await page.fill('#auth-form input[name="password"]', 'diamond99');
await page.click('[data-open-terms]');
await page.waitForTimeout(800);
await page.locator('#terms-body').evaluate(el => { el.scrollTop = el.scrollHeight; });
await page.waitForTimeout(400);
await page.click('#terms-accept');
await page.waitForTimeout(300);
await page.click('#auth-submit');
await page.waitForTimeout(2000);
await page.locator('.paygo [data-paygo]').scrollIntoViewIfNeeded();
await page.click('.paygo [data-paygo]');
await page.waitForTimeout(600);
await page.click('#paygo-options [data-topup="1000"]');
await page.waitForTimeout(800);
await page.check('#checkout-consent');
await page.click('#checkout-continue');
await page.waitForTimeout(12000);
const mountHtml = await page.evaluate(() => document.querySelector('#checkout-mount').innerHTML);
console.log('MOUNT HTML:', mountHtml);
const info = await page.evaluate(() => {
  const f = document.querySelector('#checkout-mount iframe');
  return f ? { src: f.src, w: f.width, h: f.height, rect: JSON.stringify(f.getBoundingClientRect()) } : null;
});
console.log('IFRAME:', JSON.stringify(info));
let inner = 'n/a';
try {
  const frame = page.frames().find(fr => fr !== page.mainFrame() && fr.url().includes('stripe'));
  if (frame) {
    inner = await frame.evaluate(() => document.body ? document.body.innerText.slice(0, 500) : '(no body)');
    console.log('IFRAME TEXT:', inner);
    console.log('IFRAME URL:', frame.url());
  } else console.log('no stripe frame found; frames:', page.frames().map(f => f.url()).slice(0, 8));
} catch (e) { console.log('iframe eval failed:', e.message.slice(0, 200)); }
await browser.close();
