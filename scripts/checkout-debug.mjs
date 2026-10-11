/* Reproduce the live checkout flow properly: create an account, then Stripe. */
import pw from 'file:///C:/Users/hextu/node_modules/playwright/index.js';
const { chromium } = pw;

const BASE = 'https://pink-diamond-eight.vercel.app';
const browser = await chromium.launch({ executablePath: 'C:/Users/hextu/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe' });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
page.setDefaultTimeout(15000);
const errors = [], responses = [];
page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
page.on('pageerror', e => errors.push('pageerror: ' + e.message));
page.on('response', r => { if (r.url().includes('/api/')) responses.push(r.status() + ' ' + r.request().method() + ' ' + r.url().replace(BASE, '')); });
page.on('requestfailed', r => errors.push('REQFAIL: ' + r.url().slice(0, 120) + ' :: ' + (r.failure()?.errorText || '')));

await page.goto(BASE, { waitUntil: 'networkidle' });
await page.click('#intro-skip').catch(() => {});

const email = 'e2e' + Date.now() + '@example.com';
await page.click('.text-button[data-open-auth="signin"]');
await page.waitForTimeout(400);
await page.click('#modal-switch-button');           // -> sign up
await page.waitForTimeout(300);
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
console.log('signed up:', email, '| modal:', await page.evaluate(() => document.querySelector('#auth-modal')?.className));

// pay-as-you-go -> Stripe embedded checkout
await page.locator('.paygo [data-paygo]').scrollIntoViewIfNeeded();
await page.click('.paygo [data-paygo]');
await page.waitForTimeout(600);
console.log('paygo modal:', await page.evaluate(() => document.querySelector('#paygo-modal')?.className));
await page.click('#paygo-options [data-topup="1000"]');
await page.waitForTimeout(800);
console.log('checkout modal:', await page.evaluate(() => document.querySelector('#checkout-modal')?.className));
console.log('live flag:', await page.evaluate(() => window.PinkPay && window.PinkPay.live()));
await page.check('#checkout-consent');
console.log('clicking continue...');
await page.click('#checkout-continue');
await page.waitForTimeout(9000);
console.log('--- /api responses ---');
responses.forEach(r => console.log('  ' + r));
console.log('--- errors ---');
[...new Set(errors)].forEach(e => console.log('  ' + e.slice(0, 400)));
console.log('mount visible:', await page.locator('#checkout-mount').isVisible());
console.log('mount html len:', await page.evaluate(() => document.querySelector('#checkout-mount').innerHTML.length));
console.log('review hidden:', await page.evaluate(() => document.querySelector('#checkout-review').hidden));
console.log('toast:', await page.locator('.toast').innerText().catch(() => ''));
console.log('window.Stripe loaded:', await page.evaluate(() => !!window.Stripe));
console.log('iframes in mount:', await page.evaluate(() => document.querySelectorAll('#checkout-mount iframe').length));
await page.screenshot({ path: 'C:/Users/hextu/head-coding-agent/shots/checkout-debug.png' });
await browser.close();
