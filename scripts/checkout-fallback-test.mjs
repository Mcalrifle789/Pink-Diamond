/* Checkout resilience test against the live site:
   A) normal embedded checkout still loads
   B) with js.stripe.com blocked, the fallback panel appears and the hosted
      redirect endpoint returns a real Stripe URL. */
import pw from 'file:///C:/Users/hextu/node_modules/playwright/index.js';
const { chromium } = pw;
const BASE = 'https://pink-diamond-eight.vercel.app';
const fails = [], oks = [];
const check = (n, c, e = '') => (c ? oks : fails).push(n + (e ? ' — ' + e : ''));

const browser = await chromium.launch({ executablePath: 'C:/Users/hextu/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe' });

async function signUp(page) {
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
  return email;
}
async function openTopup(page) {
  await page.locator('.paygo [data-paygo]').scrollIntoViewIfNeeded();
  await page.click('.paygo [data-paygo]');
  await page.waitForTimeout(600);
  await page.click('#paygo-options [data-topup="1000"]');
  await page.waitForTimeout(800);
  await page.check('#checkout-consent');
  await page.click('#checkout-continue');
}

/* A) normal flow */
{
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  page.setDefaultTimeout(20000);
  let topupOk = false;
  page.on('response', r => { if (r.url().includes('/api/payments/checkout/topup') && r.status() === 200) topupOk = true; });
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.click('#intro-skip').catch(() => {});
  await signUp(page);
  await openTopup(page);
  await page.waitForTimeout(10000);
  const loadingGone = await page.evaluate(() => !document.querySelector('.checkout-loading'));
  const iframe = await page.evaluate(() => {
    const f = document.querySelector('#checkout-mount iframe');
    return f ? Math.round(f.getBoundingClientRect().height) : 0;
  });
  check('normal: session created', topupOk);
  check('normal: loading cleared', loadingGone);
  check('normal: Stripe iframe sized', iframe > 200, 'h=' + iframe);
  await page.close();
}

/* B) blocked flow */
{
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  page.setDefaultTimeout(20000);
  await page.route('**://js.stripe.com/**', r => r.abort());
  let redirectUrl = null;
  page.on('response', async r => {
    if (r.url().includes('redirect=1') && r.status() === 200) {
      try { redirectUrl = (await r.json()).url; } catch { /* ignore */ }
    }
  });
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.click('#intro-skip').catch(() => {});
  await signUp(page);
  await openTopup(page);
  await page.waitForTimeout(8000);
  const fallbackShown = await page.locator('.checkout-fallback').isVisible();
  const msg = fallbackShown ? await page.locator('.checkout-fallback p').innerText() : '';
  check('blocked: fallback panel appears', fallbackShown);
  check('blocked: message mentions blockers', /ad blocker|privacy/i.test(msg), msg.slice(0, 60));
  check('blocked: back-to-review exists', await page.locator('.checkout-fallback .checkout-back').isVisible());
  await page.click('.checkout-fallback button');   // hosted fallback
  await page.waitForTimeout(4000);
  check('blocked: hosted URL returned by API', !!redirectUrl && /checkout\.stripe\.com/.test(redirectUrl), (redirectUrl || '').slice(0, 60));
  await page.click('.checkout-fallback .checkout-back').catch(() => {});
  await page.waitForTimeout(400);
  check('blocked: back returns to review', await page.evaluate(() => !document.querySelector('#checkout-review').hidden));
  await page.close();
}

await browser.close();
console.log('PASS: ' + oks.length);
oks.forEach(o => console.log('  ✓ ' + o));
if (fails.length) { console.log('FAIL: ' + fails.length); fails.forEach(f => console.log('  ✗ ' + f)); process.exit(1); }
