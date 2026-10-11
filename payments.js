/* ============================================================
   Pink Diamond — payments client
   ------------------------------------------------------------
   · Terms & Agreement gate before an account can be created
   · Subscription checkout (monthly / yearly, optional +$10
     Uncensored Mode) with the auto-renewal disclosure and an
     explicit renewal-consent checkbox
   · Pay-as-you-go: $10 $20 $50 $100 $250 $500 or custom,
     $1 = 100 Pink Credits
   · Pink Credits balance in the agent and the profile
   · Manage billing (saved cards, invoices, cancel) via Stripe
   Card details are entered only inside Stripe's embedded
   checkout iframe; nothing here ever sees a card number.
   When the API reports payments aren't live (no Stripe keys or
   no persistent database) every flow runs as a labelled demo
   that charges nothing.
   Loads after app.js / unfiltered.js and shares their scope.
   ============================================================ */
'use strict';

(function () {
  const TERMS_FALLBACK_VERSION = '2026-10-10';
  const PLAN_CENTS = { Go: 1199, Plus: 2299, Pro: 3399, Max: 12199 };
  const UNCENSORED_CENTS = 1000;
  const TOPUP_MIN = 500, TOPUP_MAX = 100000;
  // Same arithmetic as native/payments/pd_money.zig.
  const yearCents = m => Math.floor((12 * m * 80 + 50) / 100);
  const priceFor = (m, interval) => (interval === 'year' ? yearCents(m) : m);
  const customerShare = paid => paid - Math.floor(paid / 2);
  const money = c => '$' + (c / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtCredits = c => Math.max(0, Math.floor(c)).toLocaleString('en-US');

  let cfg = null;
  let termsVersion = TERMS_FALLBACK_VERSION;
  const live = () => !!(cfg && cfg.live);

  const token = () => currentUser()?.apiToken;
  const authHeaders = () => (token() ? { Authorization: 'Bearer ' + token() } : {});
  async function api(path, opts = {}) {
    const r = await fetch(API + path, { ...opts, headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(opts.headers || {}) } });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(body.detail || ('HTTP ' + r.status)), { status: r.status });
    return body;
  }

  async function loadConfig() {
    if (API === null) return;
    try { cfg = await api('/api/payments/config'); termsVersion = cfg.terms_version || termsVersion; }
    catch { cfg = null; }
  }

  /* ======================= TERMS & AGREEMENT ======================= */
  const termsBody = $('#terms-body');
  const termsAccept = $('#terms-accept');
  const acceptBox = $('#accept-terms');
  let termsLoaded = false;

  async function loadTerms() {
    if (termsLoaded) return;
    try {
      const html = await (await fetch('legal/terms.html')).text();
      const doc = new DOMParser().parseFromString(html, 'text/html');
      const main = doc.getElementById('terms-document');
      termsVersion = main?.dataset.version || termsVersion;
      termsBody.innerHTML = '';
      termsBody.append(...[...main.childNodes].map(n => document.importNode(n, true)));
      termsLoaded = true;
    } catch {
      termsBody.innerHTML = '<p>The Terms &amp; Agreement could not be loaded. <a href="legal/terms.html" target="_blank" rel="noopener">Open them in a new tab</a>, then accept here.</p>';
      termsAccept.disabled = false;
    }
  }
  function checkTermsScroll() {
    const atEnd = termsBody.scrollTop + termsBody.clientHeight >= termsBody.scrollHeight - 24;
    if (atEnd && termsLoaded) {
      termsAccept.disabled = false;
      $('#terms-progress').textContent = "You've reached the end.";
    }
  }
  async function openTerms() {
    openModal('#terms-modal');
    await loadTerms();
    termsBody.scrollTop = 0;
    checkTermsScroll();
  }
  termsBody?.addEventListener('scroll', checkTermsScroll, { passive: true });
  termsAccept?.addEventListener('click', () => {
    acceptBox.disabled = false;
    acceptBox.checked = true;
    closeModal($('#terms-modal'));
    showToast('Terms accepted — finish creating your account.');
  });
  $$('[data-open-terms]').forEach(b => b.addEventListener('click', e => { e.preventDefault(); openTerms(); }));
  // The checkbox only unlocks after the document has been read.
  $('#terms-row')?.addEventListener('click', e => { if (acceptBox.disabled && e.target !== acceptBox) openTerms(); });

  /* ============================ BALANCE ============================ */
  async function renderBalance() {
    const user = currentUser();
    let cents = user ? Math.round((user.apiBalance || 0) * 100) : 0;
    let source = 'local';
    if (user && live() && token()) {
      try { const b = await api('/api/balance'); cents = b.remaining_cents; source = b.source; } catch { /* keep local */ }
    }
    const credits = fmtCredits(cents);              // 1 credit = 1 cent
    const low = !!user && cents <= 50;
    const set = (sel, txt) => { const el = $(sel); if (el) el.textContent = txt; };
    set('#agent-credits', credits);
    set('#agent-dollars', money(Math.max(0, cents)));
    set('#stat-credits', credits);
    set('#stat-api-balance', money(Math.max(0, cents)) + ' · ' + credits + ' Pink Credits');
    set('#api-balance-hint', low ? 'Low balance — top up or subscribe to keep using paid models'
      : '50% of every subscription payment funds it' + (source === 'openrouter' ? ' · live from OpenRouter' : ''));
    $('#agent-balance')?.classList.toggle('low', low);
    return cents;
  }

  /* ============================ CHECKOUT ============================ */
  const modal = $('#checkout-modal');
  const state = { kind: 'subscription', plan: 'Plus', interval: 'month', uncensored: false, amount: 0 };
  let embedded = null;

  function lines() {
    if (state.kind === 'topup') {
      return { total: state.amount, rows: [['Pink Credits', fmtCredits(state.amount)], ['One-time charge', money(state.amount)]] };
    }
    const plan = priceFor(PLAN_CENTS[state.plan], state.interval);
    const unc = state.uncensored ? priceFor(UNCENSORED_CENTS, state.interval) : 0;
    const rows = [[`${state.plan} plan · ${state.interval === 'year' ? 'yearly' : 'monthly'}`, money(plan)]];
    if (unc) rows.push(['Uncensored Mode (18+)', '+' + money(unc)]);
    return { total: plan + unc, rows };
  }

  function render() {
    const sub = state.kind === 'subscription';
    const { total, rows } = lines();
    const per = state.interval === 'year' ? 'year' : 'month';
    $('#checkout-kind').textContent = sub ? 'SUBSCRIPTION' : 'PAY AS YOU GO';
    $('#checkout-title').innerHTML = sub ? `${state.plan}<br /><em>${money(total)} / ${per}</em>` : `Add credits<br /><em>${fmtCredits(state.amount)} Pink Credits</em>`;
    $('#checkout-interval').hidden = !sub;
    $$('#checkout-interval button').forEach(b => b.classList.toggle('active', b.dataset.interval === state.interval));
    $('#checkout-uncensored-row').hidden = !sub;
    $('#checkout-uncensored-price').textContent = '+' + money(priceFor(UNCENSORED_CENTS, state.interval)) + '/' + (per === 'year' ? 'yr' : 'mo');
    $('#checkout-adult-row').hidden = !(sub && state.uncensored);
    const share = sub ? customerShare(total) : total;
    $('#checkout-lines').innerHTML = rows.map(([k, v]) => `<div class="addon-line"><span>${k}</span><b>${v}</b></div>`).join('') +
      `<div class="addon-line addon-total"><span>${sub ? 'Due today' : 'Total'}</span><b id="checkout-total">${money(total)}</b></div>` +
      `<div class="addon-line checkout-credits"><span>${sub ? '50% becomes Pink Credits' : 'Added to your balance'}</span><b>${fmtCredits(share)} credits</b></div>`;
    $('#checkout-disclosure').textContent = sub
      ? `Renews automatically every ${per} at ${money(total)} (plus any applicable tax) until you cancel. Cancel anytime in Settings → Manage billing; cancellation takes effect at the end of the current billing period and you won't be charged again. Half of each payment (${money(share)}) becomes ${fmtCredits(share)} Pink Credits.`
      : 'One-time charge — this is not a subscription. $1 = 100 Pink Credits. Credits have no cash value and stay on your account.';
    $('#checkout-consent-text').textContent = sub
      ? `I agree that my subscription renews automatically at ${money(total)}/${per} until I cancel, under the Terms & Agreement.`
      : 'I understand Pink Credits have no cash value and are non-refundable except where the law requires.';
    const btn = $('#checkout-continue');
    btn.innerHTML = live() ? 'Continue to secure payment <span>↗</span>' : 'Confirm — demo, no charge <span>↗</span>';
    $('#checkout-note').textContent = live()
      ? 'Payments are processed by Stripe. Card details go straight to Stripe and are never stored by Pink Diamond. Cards you choose to save fill in automatically next time.'
      : "Demo mode: payments aren't live on this deployment yet, so no card is requested and nothing is charged.";
    validate();
  }

  function validate() {
    const ok = $('#checkout-consent').checked && (!state.uncensored || state.kind !== 'subscription' || $('#checkout-adult').checked);
    $('#checkout-continue').disabled = !ok;
  }

  function resetModal() {
    if (embedded) { try { embedded.destroy(); } catch { /* already gone */ } embedded = null; }
    $('#checkout-mount').hidden = true;
    $('#checkout-mount').innerHTML = '';
    $('#checkout-review').hidden = false;
    $('#checkout-consent').checked = false;
  }

  function openPlanCheckout(planKey) {
    const user = currentUser();
    if (planKey === 'Free') {
      if (live() && user && user.tier !== 'Free') {
        showToast('To move to Free, cancel auto-renewal in Settings → Manage billing.');
        return;
      }
      return applyPlanLocally('Free', 'month', false);
    }
    resetModal();
    Object.assign(state, { kind: 'subscription', plan: planKey, interval: billing === 'yearly' ? 'year' : 'month',
      uncensored: false });
    $('#checkout-uncensored').checked = false;
    $('#checkout-adult').checked = !!user?.adult;
    render();
    openModal('#checkout-modal');
  }

  function openTopup(cents) {
    if (!currentUser()) { openAuth('signup'); return showToast('Create an account to add Pink Credits.'); }
    if (!(cents >= TOPUP_MIN && cents <= TOPUP_MAX)) return showToast('Top-ups are between $5 and $1,000.');
    closeModal($('#paygo-modal'));
    resetModal();
    Object.assign(state, { kind: 'topup', amount: Math.round(cents), uncensored: false });
    render();
    openModal('#checkout-modal');
  }

  $$('#checkout-interval button').forEach(b => b.addEventListener('click', () => { state.interval = b.dataset.interval; render(); }));
  $('#checkout-uncensored')?.addEventListener('change', e => { state.uncensored = e.target.checked; render(); });
  $('#checkout-adult')?.addEventListener('change', validate);
  $('#checkout-consent')?.addEventListener('change', validate);
  modal?.querySelector('[data-close-modal]')?.addEventListener('click', resetModal);

  let stripeJs = null;
  function loadStripe() {
    if (window.Stripe) return Promise.resolve(window.Stripe);
    stripeJs = stripeJs || new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = cfg.stripe_js;
      s.onload = () => resolve(window.Stripe);
      s.onerror = () => reject(new Error('Stripe could not load'));
      document.head.appendChild(s);
    });
    return stripeJs;
  }

  async function startLiveCheckout() {
    const btn = $('#checkout-continue');
    btn.disabled = true;
    try {
      if (!token()) throw new Error('Your session expired — sign in again to pay.');
      const Stripe = await loadStripe();
      const stripe = Stripe(cfg.publishable_key);
      const path = state.kind === 'topup' ? '/api/payments/checkout/topup' : '/api/payments/checkout/subscription';
      const body = state.kind === 'topup' ? { amount_cents: state.amount } : {
        plan: state.plan.toLowerCase(), interval: state.interval, uncensored: state.uncensored,
        adult_confirmed: state.uncensored && $('#checkout-adult').checked, accept_auto_renewal: true,
      };
      embedded = await stripe.createEmbeddedCheckoutPage({
        fetchClientSecret: async () => (await api(path, { method: 'POST', body: JSON.stringify(body) })).client_secret,
      });
      $('#checkout-review').hidden = true;
      $('#checkout-mount').hidden = false;
      embedded.mount('#checkout-mount');
    } catch (err) {
      showToast(err.message || 'Checkout could not start.');
      btn.disabled = false;
    }
  }

  function confirmDemo() {
    if (state.kind === 'topup') {
      const a = accounts(), u = currentUser();
      a[u.email].apiBalance = (a[u.email].apiBalance || 0) + state.amount / 100;
      saveAccounts(a);
      window.PinkAds?.track('creditPack', { value: state.amount / 100, currency: 'USD' });
      showToast(`Demo: ${fmtCredits(state.amount)} Pink Credits added — no card was charged.`);
    } else {
      applyPlanLocally(state.plan, state.interval, state.uncensored);
    }
    closeModal(modal);
    renderBalance();
  }

  $('#checkout-continue')?.addEventListener('click', () => (live() ? startLiveCheckout() : confirmDemo()));

  /* ---- back from Stripe: ?checkout=cs_... ---- */
  async function handleReturn() {
    const id = new URLSearchParams(location.search).get('checkout');
    if (!id || !live() || !token()) return;
    history.replaceState(null, '', location.pathname + location.hash);
    try {
      const s = await api('/api/payments/session/' + encodeURIComponent(id));
      if (s.status !== 'complete') return showToast('Checkout was not completed — nothing was charged.');
      // The webhook credits the account; give it a moment, then sync.
      for (let i = 0; i < 6; i++) {
        await syncFromServer();
        if (s.mode !== 'subscription' || currentUser()?.tier !== 'Free') break;
        await new Promise(r => setTimeout(r, 1500));
      }
      showToast(s.mode === 'subscription' ? 'Payment received — your plan is active.' : 'Payment received — credits added.');
    } catch (err) { showToast(err.message); }
  }

  /* Server truth → local mirror (plan, add-on, balance). */
  async function syncFromServer() {
    if (!live() || !token()) return;
    try {
      const me = await api('/api/me');
      const a = accounts(), u = currentUser();
      if (!u) return;
      const tier = me.plan === 'free' ? 'Free' : me.plan[0].toUpperCase() + me.plan.slice(1);
      a[u.email].tier = tier;
      a[u.email].renewsAt = me.renews_at;
      if (!me.pink_mode) a[u.email].unfiltered = false;
      if (tier === 'Free') a[u.email].modelChoice = {};
      saveAccounts(a);
      renderHeat();
      renderModelPicker();
      await renderBalance();
    } catch { /* offline: keep local state */ }
  }

  /* ========================= PAY AS YOU GO ========================= */
  $$('[data-topup]').forEach(b => b.addEventListener('click', () => openTopup(Number(b.dataset.topup))));
  const custom = $('#paygo-custom');
  custom?.addEventListener('input', () => {
    const v = Number(custom.value);
    $('#paygo-custom-credits').textContent = fmtCredits(Number.isFinite(v) ? Math.round(v * 100) : 0);
  });
  $('#paygo-custom-form')?.addEventListener('submit', e => {
    e.preventDefault();
    openTopup(Math.round(Number(custom.value) * 100));
  });

  /* ========================= MANAGE BILLING ========================= */
  $('#manage-billing')?.addEventListener('click', async () => {
    if (!currentUser()) return openAuth('signin');
    if (!live()) return showToast('Billing management opens here once payments are live.');
    try { location.href = (await api('/api/payments/portal', { method: 'POST' })).url; }
    catch (err) { showToast(err.status === 404 ? 'No billing history yet — subscribe or add credits first.' : err.message); }
  });

  /* ===================== UNCENSORED MODE ADD-ON ===================== */
  async function setUncensored(enabled) {
    if (!live()) return true;                                  // demo: local only
    try {
      await api('/api/payments/uncensored', { method: 'POST', body: JSON.stringify({ enabled, adult_confirmed: true }) });
      return true;
    } catch (err) { showToast(err.message); return false; }
  }

  window.PinkPay = {
    live, openPlanCheckout, openTopup, openTerms, renderBalance, setUncensored, syncFromServer,
    termsVersion: () => termsVersion,
  };

  loadConfig().then(async () => { await syncFromServer(); await handleReturn(); renderBalance(); });
  renderBalance();
})();
