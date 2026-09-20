/* ============================================================
   Pink Diamond — UNFILTERED MODE
   ------------------------------------------------------------
   The paid add-on that separates Pink Diamond from Pale.
   Rules enforced here:
     · requires a signed-in account
     · requires a paid plan (Free cannot buy the add-on)
     · requires a one-time 18+ confirmation
     · billed as its own line, repriced with the billing period
     · switching it on changes tone, routing and credit cost
   Loads after app.js and shares its top-level scope.
   ============================================================ */
'use strict';

const HEAT = {
  price: 18,           // USD / month, on top of the plan
  yearlyFactor: 0.8,   // matches the 20% yearly saving on plans
  creditCost: 2,       // credits per unfiltered message (vs 1 filtered)
  models: ['Dolphin 3.0 R1', 'Venice Uncensored', 'Euryale 70B', 'Midnight Rose 103B', 'Grok (unfiltered)'],
};

const heatPrice = () => (billing === 'yearly' ? HEAT.price * HEAT.yearlyFactor : HEAT.price);
const heatAmount = () => '+$' + heatPrice().toFixed(2).replace(/\.00$/, '');
const heatPriceLabel = () => heatAmount() + (billing === 'yearly' ? '/mo · billed yearly' : '/mo');

const isUnfiltered = () => !!currentUser()?.unfiltered;
const isPaidPlan = () => { const u = currentUser(); return !!u && u.tier !== 'Free'; };

function patchUser(fields) {
  const u = currentUser(); if (!u) return null;
  const a = accounts();
  Object.assign(a[u.email], fields);
  saveAccounts(a);
  return a[u.email];
}

/* ---------- paint every surface that reflects the mode ---------- */
function renderHeat() {
  const on = isUnfiltered();
  const user = currentUser();
  document.documentElement.classList.toggle('heat-on', on);

  const label = heatPriceLabel();
  const setText = (sel, txt) => { const el = $(sel); if (el) el.textContent = txt; };
  const setHtml = (sel, html) => { const el = $(sel); if (el) el.innerHTML = html; };

  setText('#heat-price', heatAmount() + (billing === 'yearly' ? ' / month, billed yearly' : ' / month') + ' on any paid plan');
  setText('#setting-heat-price', label);
  setHtml('#addon-price', heatAmount() + '<i>' + (billing === 'yearly' ? '/mo yearly' : '/mo') + '</i>');
  setText('#addon-line-price', '+$' + heatPrice().toFixed(2));

  // header pill
  const pill = $('.heat-pill');
  if (pill) {
    pill.setAttribute('aria-pressed', String(on));
    pill.classList.toggle('on', on);
    pill.querySelector('.heat-pill-label').textContent = on ? 'NSFW' : 'SFW';
    pill.title = on ? 'Unfiltered Mode is on' : 'Unfiltered Mode — paid add-on';
  }

  // landing card + agent switch
  $$('.heat-switch, .agent-heat').forEach(el => {
    el.classList.toggle('on', on);
    el.setAttribute('aria-checked', String(on));
  });
  setText('#heat-badge', on ? 'ON' : 'OFF');
  setText('#heat-state-title', on ? 'Unfiltered' : 'Filtered');
  setText('#heat-state-sub', on
    ? 'No hedging · adult output enabled · ' + label
    : 'Safe defaults · included in every plan');
  setText('#heat-tone', on ? 'Blunt' : 'Measured');
  setText('#heat-adult', on ? 'Allowed (18+)' : 'Blocked');
  setText('#heat-route', on ? HEAT.models.slice(0, 2).join(' · ') : 'Guarded endpoints');
  setText('#heat-cost', on ? String(HEAT.creditCost) : '1');

  // agent shell
  $('#agent')?.classList.toggle('heat', on);
  setText('#agent-mode-tag', on ? 'UNFILTERED' : 'FILTERED');
  setText('#agent-heat-sub', (on ? 'on · ' : 'off · ') + label);
  const modelBtn = $('#agent-model');
  if (modelBtn && !modelBtn.dataset.userSet) modelBtn.textContent = on ? HEAT.models[0] : 'Nano Banana Pro';

  // settings row
  const pt = $('.heat-pill-toggle');
  if (pt) { pt.classList.toggle('on', on); pt.setAttribute('aria-pressed', String(on)); }
  setText('#setting-heat-state', on ? 'On' : 'Off');
  const revoke = $('#revoke-adult');
  if (revoke) revoke.hidden = !(user && user.adult);

  // plans add-on strip
  $('#addon-strip')?.classList.toggle('active', on);
  const addonBtn = $('#addon-strip [data-unfiltered-toggle]');
  if (addonBtn) addonBtn.innerHTML = on ? 'Remove add-on <span>↗</span>' : 'Add to plan <span>↗</span>';
}

/* ---------- the consent + purchase funnel ---------- */
function requestUnfiltered() {
  if (isUnfiltered()) return disableUnfiltered();

  if (!currentUser()) {
    store.set('pk_pending_heat', true);
    openAuth('signup');
    showToast('Unfiltered Mode needs an account — create your facet first.');
    return;
  }
  if (!isPaidPlan()) {
    store.set('pk_pending_heat', true);
    $$('.modal-backdrop.open').forEach(closeModal);
    closeAgent();
    document.getElementById('plans')?.scrollIntoView({ behavior: 'smooth' });
    showToast('Unfiltered Mode is an add-on for paid plans — pick a plan to unlock it.');
    return;
  }
  if (!currentUser().adult) { openModal('#adult-modal'); return; }
  openAddonCheckout();
}

function openAddonCheckout() {
  const user = currentUser();
  const plan = PLANS.find(p => p.key === user.tier);
  const base = plan ? (billing === 'yearly' ? plan.price * 0.8 : plan.price) : 0;
  $('#addon-plan').textContent = user.tier + ' · $' + base.toFixed(2);
  $('#addon-line-price').textContent = '+$' + heatPrice().toFixed(2);
  $('#addon-total').textContent = '$' + (base + heatPrice()).toFixed(2) +
    (billing === 'yearly' ? ' / mo billed yearly' : ' / mo');
  openModal('#addon-modal');
}

function enableUnfiltered() {
  patchUser({ unfiltered: true, unfilteredSince: new Date().toISOString() });
  renderHeat();
  window.PinkAds?.track('unfilteredAddon', { value: heatPrice(), currency: 'USD', tier: currentUser().tier });
  showToast('Unfiltered Mode is on. ' + heatPriceLabel() + ' added to your subscription.');
}

function disableUnfiltered() {
  patchUser({ unfiltered: false });
  renderHeat();
  window.PinkAds?.track('unfilteredCancel', {});
  showToast('Unfiltered Mode off. The add-on stops at the end of this period.');
}

/* ---------- wiring ---------- */
$$('[data-unfiltered-toggle]').forEach(b => b.addEventListener('click', requestUnfiltered));

$('#adult-consent')?.addEventListener('change', e => { $('#adult-continue').disabled = !e.target.checked; });
$('#adult-continue')?.addEventListener('click', () => {
  patchUser({ adult: true, adultConfirmedAt: new Date().toISOString() });
  closeModal($('#adult-modal'));
  $('#adult-consent').checked = false;
  $('#adult-continue').disabled = true;
  renderHeat();
  openAddonCheckout();
});
$('#addon-confirm')?.addEventListener('click', () => {
  closeModal($('#addon-modal'));
  enableUnfiltered();
});
$('#revoke-adult')?.addEventListener('click', () => {
  if (!confirm('Revoke your 18+ confirmation? Unfiltered Mode will be turned off.')) return;
  patchUser({ adult: false, unfiltered: false });
  renderHeat();
  showToast('18+ confirmation revoked.');
});
// remember a manual model choice so renderHeat stops overwriting it
$('#agent-model')?.addEventListener('click', () => { $('#agent-model').dataset.userSet = '1'; });

/* ---------- the unfiltered voice ---------- */
function unfilteredReply(input) {
  const t = input.toLowerCase().trim();
  const has = (...w) => w.some(x => t.includes(x));

  if (has('who are you', 'what are you', 'your name'))
    return 'Pink Diamond, unfiltered. Same engine as the polished version, none of the throat-clearing. Ask for what you actually want and I will write it.';
  if (has('can you', 'are you allowed', 'will you', 'uncensored', 'filter'))
    return 'Unfiltered Mode is on, so: yes to blunt opinions, profanity, dark themes, and explicit adult fiction between consenting adults. Still no to sexual content involving minors, sexual imagery of real people, and real instructions for weapons, drug synthesis or malware — those are hard-wired off and no subscription unlocks them.';
  if (has('story', 'fiction', 'erotic', 'nsfw', 'explicit', 'scene', 'roleplay'))
    return 'Good — give me the two characters, confirm both are adults, the setting, and how explicit you want it on a 1-10. I will write it straight through without softening the scene or breaking to check in.';
  if (has('image', 'picture', 'render', 'draw'))
    return 'For unfiltered visuals I route to uncensored open-weight checkpoints instead of the guarded APIs. Describe subject, framing, lighting and how explicit — I will build the prompt and the negative prompt without sanitising it.';
  if (has('honest', 'opinion', 'think', 'brutal', 'roast', 'critique'))
    return 'Then here is the unhedged read: most of what you are weighing does not matter, one thing does, and you already suspect which. Give me the real situation and I will say what I think instead of listing balanced considerations.';
  if (has('price', 'plan', 'cost', 'subscription', 'how much'))
    return 'Plans run Free, Port $9.99, Plus $20, Pro $45, Max $115. Unfiltered Mode is ' + heatPriceLabel() + ' on top of any paid one. It is a toggle — flip it off and the charge stops at the end of the period.';
  if (has('code', 'bug', 'function', 'error'))
    return 'Paste it. I will tell you what is wrong without the preamble about how it is a great start.';
  if (has('hi', 'hello', 'hey') || t === 'hi' || t === 'hey')
    return 'I am here and the filter is off. What do you actually want to make?';
  if (t.endsWith('?'))
    return 'Short version: ' + input.trim().replace(/\?+$/, '') + ' — my honest answer turns on one detail you have not given me. Name it and I will commit to a position rather than hedge.';
  return 'Understood — "' + input.trim() + '". Filter is off, so I will take it at face value and just do it. Tell me the format and how far to push it.';
}

/* ---------- boot ---------- */
refreshAuthUI();
renderHeat();
