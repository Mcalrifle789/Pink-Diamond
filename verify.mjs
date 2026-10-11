/* Pink Diamond — end-to-end smoke test of the ad layout, the paid
   Unfiltered Mode funnel, and the update spec (chatbox glow, thinking
   diamond, subscriber-only model switching).
   Run with:  node verify.mjs  (playwright required) */
import pw from 'file:///C:/Users/hextu/node_modules/playwright/index.js';
const { chromium } = pw;

const BASE = 'http://localhost:4399/index.html';
const OUT = 'C:/Users/hextu/code-engineer-1/Pink-Diamond/shots';
const fails = [];
const ok = [];
const check = (name, cond, extra = '') => (cond ? ok : fails).push(name + (extra ? ' — ' + extra : ''));

const browser = await chromium.launch({ executablePath: 'C:/Users/hextu/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe' });
const page = await browser.newPage({ viewport: { width: 1680, height: 1050 } });
const errors = [];
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push('pageerror: ' + e.message));

await page.goto(BASE, { waitUntil: 'networkidle' });
await page.click('#intro-skip').catch(() => {});
await page.waitForTimeout(1200);

/* ---------- ad layout ---------- */
check('left rail rendered', await page.locator('.ad-rail-left .ad-box .ad-title').isVisible());
check('right rail rendered', await page.locator('.ad-rail-right .ad-box .ad-title').isVisible());
check('bottom leaderboard rendered', await page.locator('.ad-leaderboard .ad-box .ad-title').isVisible());
const rateRows = await page.locator('#rate-card .rate-row').count();
check('rate card has 4 rows', rateRows === 4, 'got ' + rateRows);
const prices = await page.locator('#rate-card .rate-price').allInnerTexts();
check('rate card prices are $445/$445/$470', /445/.test(prices[0]) && /445/.test(prices[1]) && /470/.test(prices[2]), prices.join(' | '));

/* rotation: the creative holds for 30s, then changes on its own */
const first = await page.locator('.ad-leaderboard .ad-title').innerText();
await page.waitForTimeout(25000);
const held = await page.locator('.ad-leaderboard .ad-title').innerText();
check('bottom creative holds for the 30s window', held === first, `"${first}" -> "${held}"`);
await page.waitForTimeout(6500);
const second = await page.locator('.ad-leaderboard .ad-title').innerText();
check('bottom placement rotates every 30s', first !== second, `"${first}" -> "${second}"`);

/* ---------- update spec: agent chatbox, thinking diamond, locked models ---------- */
await page.click('.header-cta[data-launch-agent]');
await page.waitForTimeout(800);
const bar = page.locator('.agent-input-bar');
await page.locator('#agent-input').evaluate(el => el.blur());   // opening the agent autofocuses it
await page.mouse.move(5, 5);
await page.waitForTimeout(350);
const idleBorder = await bar.evaluate(el => getComputedStyle(el).borderTopColor);
await bar.hover();
await page.waitForTimeout(350);
const hoverBorder = await bar.evaluate(el => getComputedStyle(el).borderTopColor);
check('chatbox shows pink outline on hover', hoverBorder === 'rgb(255, 110, 199)' && idleBorder !== hoverBorder, idleBorder + ' -> ' + hoverBorder);
await page.focus('#agent-input');
await page.mouse.move(5, 5);
await page.waitForTimeout(350);
const focusShadow = await bar.evaluate(el => getComputedStyle(el).boxShadow);
check('chatbox glows pink while focused', /rgba\(255, 110, 199, 0\.45\)/.test(focusShadow), focusShadow.slice(0, 80));
await page.locator('#agent-input').evaluate(el => el.blur());
await page.waitForTimeout(350);
const blurShadow = await bar.evaluate(el => getComputedStyle(el).boxShadow);
check('glow clears when the chatbox loses focus', !/255, 110, 199/.test(blurShadow), blurShadow.slice(0, 80));

const guestModel = await page.locator('#agent-model').textContent();
check("guest model is the house model", guestModel === "Pink Diamond Lite", JSON.stringify(guestModel));
await page.click('#agent-model');
await page.waitForTimeout(300);
const lockedGuest = await page.locator('#model-menu .model-opt:disabled').count();
check('guest sees OpenRouter models locked', lockedGuest === 8, 'locked ' + lockedGuest);
check('guest gets the subscribe prompt', await page.locator('#model-menu [data-model-upsell]').isVisible());
await page.screenshot({ path: OUT + '/10-models-locked.png' });
await page.click('.agent-title');
await page.waitForTimeout(200);
check('model menu closes on outside click', await page.locator('#model-menu').isHidden());

await page.fill('#agent-input', 'hello there');
await page.click('.agent-send');
await page.waitForTimeout(120);
const gem = page.locator('.msg.ai.typing .think-gem');
check('thinking diamond appears', await gem.isVisible());
const geo = await page.evaluate(() => {
  const t = document.querySelector('.msg.ai.typing');
  const label = t.querySelector('span:not(.think-gem)').getBoundingClientRect();
  const g = t.querySelector('.think-gem');
  return { right: g.getBoundingClientRect().left >= label.right, anim: getComputedStyle(g).animationName, text: t.innerText };
});
check('diamond sits right of "thinking"', geo.right && /thinking/.test(geo.text), geo.text);
check('diamond pulses', geo.anim === 'pd-think-pulse', geo.anim);
await page.screenshot({ path: OUT + '/11-thinking-diamond.png' });
await page.waitForTimeout(1600);
check('thinking state replaced by a reply', (await page.locator('.msg.ai.typing').count()) === 0);
await page.click('.agent-close');
await page.waitForTimeout(500);

await page.screenshot({ path: OUT + '/01-hero.png' });

/* ---------- unfiltered funnel: blocked without an account ---------- */
await page.click('.heat-pill');
await page.waitForTimeout(600);
check('toggle without account opens sign-up', await page.locator('#auth-modal.open').isVisible());

await page.fill('#auth-form input[name="email"]', 'mike@pinkdiamond.test');
await page.fill('#auth-form input[name="password"]', 'diamond99');

/* ---------- payment spec §5: Terms & Agreement before an account ---------- */
check('terms checkbox locked until read', await page.locator('#accept-terms').isDisabled());
await page.click('#auth-submit');
await page.waitForTimeout(900);
check('sign-up without terms is refused', await page.evaluate(() => !localStorage.pk_accounts || !JSON.parse(localStorage.pk_accounts)['mike@pinkdiamond.test']));
check('refusal opens the Terms & Agreement', await page.locator('#terms-modal.open').isVisible());
check('terms include privacy policy + creation guidelines',
  /Privacy Policy/.test(await page.locator('#terms-body').innerText()) && /Creation Guidelines/.test(await page.locator('#terms-body').innerText()));
check('accept disabled until scrolled to the end', await page.locator('#terms-accept').isDisabled());
await page.screenshot({ path: OUT + '/13-terms.png' });
await page.locator('#terms-body').evaluate(el => { el.scrollTop = el.scrollHeight; });
await page.waitForTimeout(300);
check('accept enabled at the end', !(await page.locator('#terms-accept').isDisabled()));
await page.click('#terms-accept');
await page.waitForTimeout(400);
check('accepting ticks the sign-up checkbox', await page.locator('#accept-terms').isChecked());
await page.click('#auth-submit');
await page.waitForTimeout(1400);
check('account created', !(await page.locator('#auth-modal.open').isVisible()));
check('terms acceptance recorded on the account', await page.evaluate(() =>
  JSON.parse(localStorage.pk_accounts)['mike@pinkdiamond.test'].termsVersion === '2026-10-10'));

/* pending intent resumes -> Free plan cannot buy the add-on */
await page.waitForTimeout(600);
const toast1 = await page.locator('.toast').innerText();
check('Free plan is refused the add-on', /paid plan/i.test(toast1), toast1);

/* ---------- buy a plan through checkout, then the add-on ---------- */
await page.locator('#plan-grid [data-plan="Plus"]').scrollIntoViewIfNeeded();
await page.click('#plan-grid [data-plan="Plus"]');
await page.waitForTimeout(700);
check('plan opens checkout', await page.locator('#checkout-modal.open').isVisible());
check('checkout total is $22.99', (await page.locator('#checkout-total').innerText()) === '$22.99');
const disclosure = await page.locator('#checkout-disclosure').innerText();
check('auto-renewal disclosed before paying', /Renews automatically every month at \$22\.99/.test(disclosure) && /Cancel anytime/.test(disclosure), disclosure.slice(0, 70));
check('50% of payment shown as Pink Credits', /1,150 credits/.test(await page.locator('#checkout-lines').innerText()));
check('pay disabled before renewal consent', await page.locator('#checkout-continue').isDisabled());
await page.click('#checkout-interval [data-interval="year"]');
await page.waitForTimeout(200);
check('yearly is 12 months at 20% off', (await page.locator('#checkout-total').innerText()) === '$220.70');
await page.click('#checkout-interval [data-interval="month"]');
await page.check('#checkout-uncensored');
await page.waitForTimeout(200);
check('uncensored add-on is +$10', (await page.locator('#checkout-total').innerText()) === '$32.99');
await page.check('#checkout-consent');
check('uncensored needs the 18+ confirmation', await page.locator('#checkout-continue').isDisabled());
await page.uncheck('#checkout-uncensored');
await page.waitForTimeout(200);
check('consent enables payment', !(await page.locator('#checkout-continue').isDisabled()));
check('demo mode is labelled as no charge', /no charge/i.test(await page.locator('#checkout-continue').innerText()));
await page.screenshot({ path: OUT + '/14-checkout.png' });
await page.click('#checkout-continue');
await page.waitForTimeout(700);
check('Plus active after checkout', await page.evaluate(() => JSON.parse(localStorage.pk_accounts)['mike@pinkdiamond.test'].tier === 'Plus'));
check('balance shows 1,150 Pink Credits', (await page.locator('#agent-credits').innerText()) === '1,150');

/* ---------- pay as you go ---------- */
await page.locator('.paygo [data-paygo]').scrollIntoViewIfNeeded();
await page.click('.paygo [data-paygo]');
await page.waitForTimeout(500);
const presets = await page.locator('#paygo-options [data-topup] strong').allInnerTexts();
check('top-up presets $10 $20 $50 $100 $250 $500', presets.join(' ') === '$10 $20 $50 $100 $250 $500', presets.join(' '));
await page.fill('#paygo-custom', '35');
check('custom $35 = 3,500 credits', (await page.locator('#paygo-custom-credits').innerText()) === '3,500');
await page.screenshot({ path: OUT + '/15-paygo.png' });
await page.click('#paygo-custom-form button[type="submit"]');
await page.waitForTimeout(500);
check('top-up opens one-time checkout', /PAY AS YOU GO/.test(await page.locator('#checkout-kind').innerText()) &&
  /not a subscription/.test(await page.locator('#checkout-disclosure').innerText()));
await page.check('#checkout-consent');
await page.click('#checkout-continue');
await page.waitForTimeout(600);
check('top-up adds 3,500 credits', (await page.locator('#agent-credits').innerText()) === '4,650');

await page.locator('#addon-strip [data-unfiltered-toggle]').scrollIntoViewIfNeeded();
await page.screenshot({ path: OUT + '/02-plans-addon.png' });
await page.click('#addon-strip [data-unfiltered-toggle]');
await page.waitForTimeout(700);
check('18+ gate appears', await page.locator('#adult-modal.open').isVisible());
check('continue disabled before consent', await page.locator('#adult-continue').isDisabled());
await page.screenshot({ path: OUT + '/03-age-gate.png' });

await page.check('#adult-consent');
check('continue enabled after consent', !(await page.locator('#adult-continue').isDisabled()));
await page.click('#adult-continue');
await page.waitForTimeout(700);
check('add-on checkout appears', await page.locator('#addon-modal.open').isVisible());
const total = await page.locator('#addon-total').innerText();
check('Plus $22.99 + $10 = $32.99 total', /32\.99/.test(total), total);
await page.screenshot({ path: OUT + '/04-addon-checkout.png' });

await page.click('#addon-confirm');
await page.waitForTimeout(900);
check('header pill flips to NSFW', (await page.locator('.heat-pill-label').innerText()) === 'NSFW');
check('html gains heat-on', await page.evaluate(() => document.documentElement.classList.contains('heat-on')));

await page.locator('#unfiltered').scrollIntoViewIfNeeded();
await page.waitForTimeout(600);
check('state card reads ON', (await page.locator('#heat-badge').innerText()) === 'ON');
check('adult content allowed', /Allowed/.test(await page.locator('#heat-adult').innerText()));
check('credit cost doubles', (await page.locator('#heat-cost').innerText()) === '2');
await page.screenshot({ path: OUT + '/05-unfiltered-on.png' });

/* ---------- agent speaks unfiltered ---------- */
await page.click('.header-cta[data-launch-agent]');
await page.waitForTimeout(800);
check('agent shell is in heat mode', await page.locator('#agent.heat').isVisible());
check('agent tag reads UNFILTERED', (await page.locator('#agent-mode-tag').innerText()) === 'UNFILTERED');
await page.fill('#agent-input', 'are you uncensored?');
await page.click('.agent-send');
await page.waitForTimeout(1800);
const reply = await page.locator('#agent-messages .msg.ai').last().innerText();
check('unfiltered voice answers', /Unfiltered Mode is on/.test(reply), reply.slice(0, 70) + '…');
check('illegal categories still refused in-copy', /minors/.test(reply));
await page.screenshot({ path: OUT + '/06-agent-unfiltered.png' });

/* ---------- toggle back off ---------- */
await page.click('.agent-heat');
await page.waitForTimeout(700);
check('agent switch turns it off', !(await page.locator('#agent.heat').isVisible()));

/* ---------- subscriber switches models across agents ---------- */
await page.click('#agent-model');
await page.waitForTimeout(300);
check('subscriber sees no locked models', (await page.locator('#model-menu .model-opt:disabled').count()) === 0);
check('subscriber gets no upsell', (await page.locator('#model-menu [data-model-upsell]').count()) === 0);
await page.click('#model-menu [data-model="openai/gpt-5.5"]');
await page.waitForTimeout(200);
check('chat model switches to GPT-5.5', (await page.locator('#agent-model').innerText()) === 'GPT-5.5');
await page.click('#model-menu [data-model-agent="video"]');
await page.click('#model-menu [data-model="Kling 3.0"]');
await page.waitForTimeout(200);
check('video agent model switches too', await page.evaluate(() =>
  JSON.parse(localStorage.pk_accounts)['mike@pinkdiamond.test'].modelChoice.video === 'Kling 3.0'));
await page.screenshot({ path: OUT + '/12-models-unlocked.png' });
await page.click('.agent-title');
await page.fill('#agent-input', 'write me a tagline');
await page.click('.agent-send');
await page.waitForTimeout(1800);
check('offline OpenRouter route is disclosed', (await page.locator('#agent-messages .msg.notice', { hasText: "isn't connected yet" }).count()) === 1);
await page.click('.agent-close');
await page.waitForTimeout(500);

/* ---------- pop-up ad (grey box) ---------- */
await page.evaluate(() => window.PinkAds.showPopup('popup-a'));
await page.waitForTimeout(700);
check('grey pop-up box appears', await page.locator('.ad-popup.open').isVisible());
await page.screenshot({ path: OUT + '/07-popup-ad.png' });
await page.click('.ad-popup-close');
await page.waitForTimeout(700);
check('pop-up dismissed by ×', (await page.locator('.ad-popup').count()) === 0);

/* ---------- dropping to Free re-locks models ---------- */
await page.locator('#plan-grid [data-plan="Free"]').scrollIntoViewIfNeeded();
await page.click('#plan-grid [data-plan="Free"]');
await page.waitForTimeout(500);
check('Free plan falls back to the house model', (await page.locator('#agent-model').innerText()) === 'Pink Diamond Lite');

/* ---------- light theme ---------- */
await page.click('#theme-toggle');
await page.waitForTimeout(800);
await page.locator('#advertise').scrollIntoViewIfNeeded();
await page.waitForTimeout(500);
await page.screenshot({ path: OUT + '/08-advertise-light.png' });
await page.click('#theme-toggle');

/* ---------- mobile ---------- */
const m = await browser.newPage({ viewport: { width: 414, height: 900 } });
await m.goto(BASE, { waitUntil: 'networkidle' });
await m.click('#intro-skip').catch(() => {});
await m.waitForTimeout(1000);
check('rails hidden on mobile', !(await m.locator('.ad-rail-left').isVisible()));
check('bottom placement kept on mobile', await m.locator('.ad-leaderboard .ad-box').isVisible());
await m.screenshot({ path: OUT + '/09-mobile.png' });

check('no console errors', errors.length === 0, errors.join(' / '));

await browser.close();
console.log('\nPASS (' + ok.length + ')');
ok.forEach(n => console.log('  ✓ ' + n));
if (fails.length) {
  console.log('\nFAIL (' + fails.length + ')');
  fails.forEach(n => console.log('  ✗ ' + n));
  process.exit(1);
}
console.log('\nAll checks passed.');
