'use strict';

/* ============================================================
   Pink Diamond — front-end app
   ============================================================ */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const store = {
  get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set: (k, v) => localStorage.setItem(k, JSON.stringify(v)),
};

/* ---------- toast ---------- */
const toast = $('.toast');
function showToast(msg) {
  toast.textContent = msg;
  toast.classList.add('show');
  clearTimeout(showToast.t);
  showToast.t = setTimeout(() => toast.classList.remove('show'), 3200);
}
window.showToast = showToast;

/* ============ INTRO: dancing diamond + vortex logo ============ */
(function intro() {
  const overlay = $('#intro');
  if (!overlay) return;
  const finish = () => overlay.classList.add('done');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce || window.location.hash) { finish(); return; }   // skip on deep links / reduced motion
  overlay.setAttribute('aria-hidden', 'false');
  setTimeout(() => overlay.classList.add('forming'), 1100);
  const timer = setTimeout(finish, reduce ? 900 : 3200);
  $('#intro-skip')?.addEventListener('click', () => { clearTimeout(timer); finish(); });
})();

/* ============ THEME ============ */
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  document.body.setAttribute('data-theme', theme);
  store.set('pk_theme', theme);
  const icon = $('.theme-icon'); if (icon) icon.textContent = theme === 'dark' ? '◐' : '◑';
  const ts = $('#theme-setting'); if (ts) ts.querySelector('span').textContent = theme === 'dark' ? 'Dark' : 'Bright';
}
applyTheme(store.get('pk_theme', 'dark'));
$('#theme-toggle')?.addEventListener('click', () =>
  applyTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark'));

/* ============ SCROLL DIAMOND (spins by scroll direction) ============ */
(function scrollDiamond() {
  const el = $('.scroll-diamond');
  if (!el) return;
  const svg = el.querySelector('svg');
  let last = window.scrollY, angle = 0;
  window.addEventListener('scroll', () => {
    const y = window.scrollY;
    const delta = y - last; last = y;
    angle += delta * 0.4;                 // down => clockwise, up => counter-clockwise
    svg.style.transform = `rotate(${angle}deg)`;
    el.classList.toggle('show', y > 260);
  }, { passive: true });
})();

/* ============ MAGNETIC + GRAVITY BUTTONS ============ */
$$('.magnetic').forEach(btn => {
  btn.addEventListener('mousemove', e => {
    const r = btn.getBoundingClientRect();
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    btn.style.setProperty('--mx', mx + 'px');
    btn.style.setProperty('--my', my + 'px');
    const px = (mx / r.width - 0.5), py = (my / r.height - 0.5);
    btn.style.transform = `translate(${px * 10}px, ${py * 8}px)`;
  });
  btn.addEventListener('mouseleave', () => { btn.style.transform = ''; });
});

/* ============ ACCOUNTS ============ */
function accounts() { return store.get('pk_accounts', {}); }
function saveAccounts(a) { store.set('pk_accounts', a); }
function currentEmail() { return store.get('pk_session', null); }
function currentUser() { const e = currentEmail(); return e ? accounts()[e] : null; }
function makeKey() {
  const seg = () => Math.random().toString(36).slice(2, 6).toUpperCase();
  return `pkd_${seg()}${seg()}_${seg()}${seg()}`;
}

function refreshAuthUI() {
  const user = currentUser();
  const signInBtn = $('[data-open-auth="signin"]');
  const avatar = $('#avatar-button');
  if (user) {
    signInBtn.hidden = true;
    avatar.hidden = false;
    avatar.textContent = user.email[0].toUpperCase();
    const an = $('.agent-account-name'); if (an) an.textContent = user.email.split('@')[0];
    const aa = $('.agent-account-avatar'); if (aa) aa.textContent = user.email[0].toUpperCase();
  } else {
    signInBtn.hidden = false;
    avatar.hidden = true;
    const an = $('.agent-account-name'); if (an) an.textContent = 'Guest';
    const aa = $('.agent-account-avatar'); if (aa) aa.textContent = 'G';
  }
}

/* ============ MODAL HELPERS ============ */
function openModal(id) { const m = $(id); m.classList.add('open'); m.setAttribute('aria-hidden', 'false'); }
function closeModal(m) { m.classList.remove('open'); m.setAttribute('aria-hidden', 'true'); }
$$('[data-close-modal]').forEach(b => b.addEventListener('click', () => closeModal(b.closest('.modal-backdrop'))));
$$('.modal-backdrop').forEach(bd => bd.addEventListener('click', e => { if (e.target === bd) closeModal(bd); }));

/* ---------- auth modal ---------- */
let authMode = 'signup';
const authModal = $('#auth-modal');
function openAuth(mode = 'signup') {
  authMode = mode;
  const signin = mode === 'signin';
  $('#modal-mode-label').textContent = signin ? 'SIGN IN' : 'WELCOME';
  $('#modal-title').innerHTML = signin ? 'Welcome<br /><em>back.</em>' : 'Make room for<br /><em>better work.</em>';
  $('#modal-subtitle').textContent = signin ? 'Pick up where you left off.' : 'Create your private facet in a few seconds.';
  $('#auth-submit').innerHTML = signin ? 'Enter facet <span>↗</span>' : 'Create facet <span>↗</span>';
  $('#modal-switch-copy').textContent = signin ? 'New to Pink Diamond?' : 'Already have an account?';
  $('#modal-switch-button').textContent = signin ? 'Create an account' : 'Sign in';
  openModal('#auth-modal');
  setTimeout(() => authModal.querySelector('input')?.focus(), 100);
}
$$('[data-open-auth]').forEach(b => b.addEventListener('click', () => openAuth(b.dataset.openAuth)));
$('#modal-switch-button').addEventListener('click', () => openAuth(authMode === 'signup' ? 'signin' : 'signup'));

$('#auth-form').addEventListener('submit', e => {
  e.preventDefault();
  const data = new FormData(e.target);
  const email = String(data.get('email')).trim().toLowerCase();
  const password = String(data.get('password'));
  const acc = accounts();
  if (authMode === 'signup') {
    if (acc[email]) return showToast('That account already exists — try signing in.');
    acc[email] = { email, password, created: new Date().toISOString(), tier: 'Free', credits: 0, apiKey: makeKey(),
      models: ['Nano Banana Pro', 'Seedance 2.5'], adult: false, unfiltered: false };
    saveAccounts(acc);
    store.set('pk_session', email);
    showToast('Your private facet is ready. A hidden API key was issued.');
    window.PinkAds?.track('signup', { tier: 'Free' });
  } else {
    if (!acc[email] || acc[email].password !== password) return showToast('Email or password not recognized.');
    store.set('pk_session', email);
    showToast(`Welcome back, ${email.split('@')[0]}.`);
  }
  e.target.reset();
  closeModal(authModal);
  refreshAuthUI();
  renderHeat();
  const pending = store.get('pk_pending_heat', false);
  if (pending) { store.set('pk_pending_heat', false); setTimeout(requestUnfiltered, 400); }
});

/* ============ PROFILE + SETTINGS ============ */
function fmtDate(iso) { return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); }
function ageString(iso) {
  const days = Math.max(0, Math.floor((Date.now() - new Date(iso)) / 864e5));
  if (days < 1) return 'New today';
  if (days < 30) return `${days} day${days > 1 ? 's' : ''}`;
  if (days < 365) return `${Math.floor(days / 30)} month${days >= 60 ? 's' : ''}`;
  return `${(days / 365).toFixed(1)} years`;
}
function openProfile() {
  const user = currentUser();
  if (!user) return openAuth('signin');
  $('#profile-avatar').textContent = user.email[0].toUpperCase();
  $('#profile-name').textContent = user.email.split('@')[0];
  $('#profile-email').textContent = user.email;
  $('#stat-tier').textContent = user.tier;
  $('#stat-created').textContent = fmtDate(user.created);
  $('#stat-age').textContent = ageString(user.created);
  $('#stat-credits').textContent = user.credits;
  renderHeat();
  // credit timeline (deterministic-ish demo based on account)
  const bars = $('#timeline-bars'); bars.innerHTML = '';
  for (let i = 0; i < 16; i++) {
    const b = document.createElement('i');
    b.style.height = (10 + Math.round((Math.sin(i * 1.7 + user.email.length) * 0.5 + 0.5) * 54)) + 'px';
    bars.appendChild(b);
  }
  openModal('#profile-modal');
}
$('#avatar-button')?.addEventListener('click', openProfile);
$('#agent-account')?.addEventListener('click', openProfile);
$$('[data-open-settings]').forEach(b => b.addEventListener('click', () => { openProfile(); switchProfileTab('settings'); }));

function switchProfileTab(tab) {
  $$('.profile-tabs button').forEach(b => b.classList.toggle('active', b.dataset.profileTab === tab));
  $$('.profile-panel').forEach(p => p.hidden = p.dataset.panel !== tab);
}
$$('.profile-tabs button').forEach(b => b.addEventListener('click', () => switchProfileTab(b.dataset.profileTab)));

$('#theme-setting')?.addEventListener('click', () =>
  applyTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark'));

$('#change-pass')?.addEventListener('click', () => {
  const user = currentUser(); if (!user) return;
  const np = prompt('Enter a new password (min 6 chars):');
  if (np && np.length >= 6) { const a = accounts(); a[user.email].password = np; saveAccounts(a); showToast('Password updated.'); }
  else if (np !== null) showToast('Password too short.');
});
$('#add-models')?.addEventListener('click', () => {
  const user = currentUser(); if (!user) return;
  const pick = prompt('Add a model (e.g. Sora 2, Google Veo 3.1, GPT Image 2, Kling 3.0):');
  if (pick) { const a = accounts(); a[user.email].models = [...new Set([...(a[user.email].models || []), pick.trim()])]; saveAccounts(a); showToast(`Added ${pick.trim()} to your models.`); }
});
$('#switch-account')?.addEventListener('click', () => { closeModal($('#profile-modal')); openAuth('signin'); });
$('#sign-out')?.addEventListener('click', () => { store.set('pk_session', null); closeModal($('#profile-modal')); refreshAuthUI(); renderHeat(); showToast('Signed out.'); });
$('#delete-account')?.addEventListener('click', () => {
  const user = currentUser(); if (!user) return;
  if (confirm('Permanently delete this account? This cannot be undone.')) {
    const a = accounts(); delete a[user.email]; saveAccounts(a);
    store.set('pk_session', null); closeModal($('#profile-modal')); refreshAuthUI(); renderHeat();
    showToast('Account deleted.');
  }
});

/* ============ PLANS (data-driven) ============ */
const PLANS = [
  { key: 'Free', name: 'Free', price: 0, desc: 'Open-weight models. Feel the cut before you commit.',
    images: 'Open-weight', videos: '—',
    quota: ['<b>Open-weight</b> models only', 'Core workspace & agent', 'Limited daily usage', 'Upgrade anytime — keep your facet'] },
  { key: 'Port', name: 'Port', price: 9.99, desc: 'A polished entry into creation.',
    images: '~1,330', videos: '16',
    quota: ['<b>~1,330</b> budget image gens', '~160 mid · ~67 premium · ~33 high-end', '<b>16</b> budget 5s videos', '8 mid · 3–4 premium videos'] },
  { key: 'Plus', name: 'Plus', price: 20, featured: true, desc: 'The recommended everyday facet — Standard quotas.',
    images: '~2,660', videos: '32',
    quota: ['<b>~2,660</b> budget image gens', '~320 mid · ~133 premium · ~67 high-end', '<b>32</b> budget 5s videos', '16 mid · 5–8 premium videos'] },
  { key: 'Pro', name: 'Pro', price: 45, desc: 'For people building at full speed.',
    images: '~5,000', videos: '60',
    quota: ['<b>~5,000</b> budget image gens', '~600 mid · ~250 premium · ~125 high-end', '<b>60</b> budget 5s videos', '30 mid · 10–15 premium videos'] },
  { key: 'Max', name: 'Max', price: 115, desc: 'Maximum brilliance, maximum output.',
    images: '~16,660', videos: '200',
    quota: ['<b>~16,660</b> budget image gens', '~2,000 mid · ~833 premium · ~417 high-end', '<b>200</b> budget 5s videos', '100 mid · 33–50 premium videos'] },
];
let billing = 'monthly';
function renderPlans() {
  const grid = $('#plan-grid'); if (!grid) return;
  grid.innerHTML = PLANS.map(p => {
    const monthly = billing === 'monthly';
    const val = p.price === 0 ? 0 : (monthly ? p.price : (p.price * 0.8));
    const price = `$${val.toFixed(2).replace(/\.00$/, '')}`;
    const suffix = p.price === 0 ? '/ forever' : (monthly ? '/ month' : '/ mo · billed yearly');
    return `<article class="plan-card glass${p.featured ? ' featured' : ''}">
      ${p.featured ? '<div class="popular-tag">RECOMMENDED</div>' : ''}
      <span class="plan-eyebrow">${p.name.toUpperCase()}</span>
      <h3>${p.name}</h3>
      <p class="plan-desc">${p.desc}</p>
      <div class="price"><b>${price}</b><span>${suffix}</span></div>
      <ul class="plan-quota">${p.quota.map(q => `<li>${q}</li>`).join('')}</ul>
      <button class="plan-button${p.featured ? ' light' : ''} magnetic" data-plan="${p.key}">Choose ${p.name} <span>↗</span></button>
    </article>`;
  }).join('');
  $$('#plan-grid [data-plan]').forEach(b => b.addEventListener('click', () => {
    const plan = b.dataset.plan;
    const user = currentUser();
    if (user) {
      const a = accounts(); a[user.email].tier = plan;
      if (plan === 'Free') { a[user.email].unfiltered = false; }
      saveAccounts(a); showToast(`${plan} is now your plan.`);
      window.PinkAds?.track('subscribe', { tier: plan, value: PLANS.find(x => x.key === plan)?.price || 0, currency: 'USD' });
      renderHeat();
    }
    else { store.set('pk_pending_plan', plan); openAuth('signup'); showToast(`${plan} selected — create your facet to continue.`); }
  }));
  // re-bind magnetic on freshly created buttons
  $$('#plan-grid .magnetic').forEach(bindMagnetic);
}
function bindMagnetic(btn) {
  btn.addEventListener('mousemove', e => {
    const r = btn.getBoundingClientRect();
    btn.style.setProperty('--mx', (e.clientX - r.left) + 'px');
    btn.style.setProperty('--my', (e.clientY - r.top) + 'px');
  });
}
$$('.billing-toggle button').forEach(b => b.addEventListener('click', () => {
  $$('.billing-toggle button').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  billing = b.dataset.billing;
  renderPlans();
  renderHeat();
  showToast(billing === 'yearly' ? 'Yearly billing — 20% saved.' : 'Monthly billing selected.');
}));
renderPlans();

/* ============ PAY AS YOU GO ============ */
$('[data-paygo]')?.addEventListener('click', () => openModal('#paygo-modal'));
$$('[data-credits]').forEach(b => b.addEventListener('click', () => {
  const c = Number(b.dataset.credits);
  const user = currentUser();
  if (user) { const a = accounts(); a[user.email].credits = (a[user.email].credits || 0) + c * 10; saveAccounts(a); }
  closeModal($('#paygo-modal'));
  window.PinkAds?.track('creditPack', { value: c, currency: 'USD' });
  showToast(`A $${c} credit pack was added.`);
}));

/* ============ AGENT (chatbox + client-side AI) ============ */
const agent = $('#agent');
function openAgent() { agent.classList.add('open'); document.documentElement.classList.add('agent-open'); agent.setAttribute('aria-hidden', 'false'); setTimeout(() => $('#agent-input')?.focus(), 120); }
function closeAgent() { agent.classList.remove('open'); document.documentElement.classList.remove('agent-open'); agent.setAttribute('aria-hidden', 'true'); }
$$('[data-launch-agent]').forEach(b => {
  b.addEventListener('click', openAgent);
  b.addEventListener('keydown', e => { if (e.key === 'Enter') openAgent(); });
});
$('[data-close-agent]')?.addEventListener('click', closeAgent);
document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeAgent(); $$('.modal-backdrop.open').forEach(closeModal); } });

$$('.agent-nav-item[data-agent-view]').forEach(b => b.addEventListener('click', () => {
  $$('.agent-nav-item').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  const view = b.dataset.agentView;
  const views = {
    conversations: 'Your saved conversations will appear here.',
    packages: 'Packages bundle models and credits — Port, Standard, Pro, Max.',
    models: 'Image: Nano Banana Pro, Seedream 5, FLUX.2, GPT Image 2, Recraft V4.1 · Video: Kling 3.0, Seedance 2.5, Veo 3.1, Sora 2, Minimax Hailuo.',
    analytics: 'Usage analytics: credits, generations, and model mix over time.',
    help: 'Type a message below and Pink Diamond will respond. Ask for plans, drafts, ideas, or code.',
  };
  if (views[view]) addMsg('ai', views[view]);
}));

$('#agent-model')?.addEventListener('click', () => {
  const m = prompt('Choose a model:', $('#agent-model').textContent);
  if (m) { $('#agent-model').textContent = m.trim(); showToast(`Model set to ${m.trim()}.`); }
});

const messagesEl = $('#agent-messages');
function addMsg(role, text) {
  $('.agent-welcome')?.remove();
  const el = document.createElement('div');
  el.className = `msg ${role}`;
  el.textContent = text;
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}

/* --- small intent-aware responder --- */
function agentReply(input) {
  const t = input.toLowerCase().trim();
  const has = (...w) => w.some(x => t.includes(x));
  if (has('hi', 'hello', 'hey', 'yo ') || t === 'hi' || t === 'hey')
    return "Hello — I'm Pink Diamond. Tell me what you're working on and I'll help you cut it down to a clear next step.";
  if (has('who are you', 'what are you', 'your name'))
  return "I'm Pink Diamond, a web-hosted AI agent for tasks, automation, and image & video creation. Think of me as a facet between your idea and the outcome.";
  if (has('price', 'plan', 'cost', 'subscription', 'how much'))
    return "Five ways in: Free (open-weight models), Port $9.99, Plus $20 (recommended, Standard quotas), Pro $45, and Max $115 — each with image & video generation quotas, plus pay-as-you-go credits. Want the breakdown for one of them?";
  if (has('image', 'picture', 'photo', 'render', 'draw', 'generate an'))
    return "For images I route to models like Nano Banana Pro, Seedream 5, FLUX.2, or GPT Image 2 depending on quality and budget. Describe the shot — subject, style, mood — and I'll turn it into a generation-ready prompt.";
  if (has('video', 'clip', 'animation', 'motion'))
    return "For 5-second clips I can reach Kling 3.0, Seedance 2.5, Veo 3.1 or Sora 2. Give me the scene and pacing and I'll storyboard it, then draft the generation prompt.";
  if (has('plan', 'roadmap', 'strategy', 'launch'))
    return "Here's a shape you can steal: 1) Frame the goal and success metric. 2) List the 3 hardest unknowns. 3) Assign an owner + date to each. Tell me the project and I'll fill it in.";
  if (has('write', 'draft', 'email', 'copy', 'post'))
    return "Happy to draft it. Give me the audience, the one thing they should do after reading, and the tone — and I'll write a first version you can trim.";
  if (has('code', 'bug', 'function', 'python', 'javascript', 'typescript', 'error'))
    return "Share the snippet and what you expected vs. what happened. I'll read it, explain the likely cause, and give you a corrected version.";
  if (has('summar', 'tl;dr', 'shorten'))
    return "Paste the text and I'll return a tight summary: the core claim, the 3 supporting points, and the one thing to remember.";
  if (has('thank'))
    return "Anytime. Bring me the next messy middle whenever you're ready.";
  if (t.endsWith('?'))
    return `Good question. Here's how I'd approach "${input.trim()}": start from what a great answer looks like, work backward to the facts you'd need, then close the gaps one at a time. Want me to go deeper on any part?`;
  return `Got it — "${input.trim()}". I read that as a task to move forward. The clearest next step is to name the outcome you want, then I'll break it into the two or three moves that get you there. What does "done" look like?`;
}

$('#agent-form')?.addEventListener('submit', e => {
  e.preventDefault();
  const input = $('#agent-input');
  const text = input.value.trim();
  if (!text) return;
  addMsg('user', text);
  input.value = '';
  const typing = addMsg('ai', isUnfiltered() ? 'Pink Diamond is thinking — unfiltered…' : 'Pink Diamond is thinking…');
  typing.classList.add('typing');
  setTimeout(() => {
    typing.remove();
    addMsg('ai', isUnfiltered() ? unfilteredReply(text) : agentReply(text));
    const user = currentUser();
    if (user) {
      const a = accounts();
      a[user.email].credits = (a[user.email].credits || 0) + (isUnfiltered() ? HEAT.creditCost : 1);
      saveAccounts(a);
    }
  }, 650 + Math.random() * 500);
});

/* ============ misc ============ */
$('.ad-window-top button')?.addEventListener('click', e => {
  const w = e.currentTarget.closest('.ad-window');
  w.style.opacity = '0'; w.style.transform = 'rotate(3deg) scale(.96)';
  showToast('Ad dismissed. Your attention stays yours.');
});
$('.menu-button')?.addEventListener('click', () => {
  const nav = $('.main-nav');
  const open = nav.style.display === 'flex';
  if (open) { nav.removeAttribute('style'); }
  else { Object.assign(nav.style, { display: 'flex', position: 'absolute', top: '72px', left: '0', right: '0', padding: '22px 24px', background: 'var(--panel)', flexDirection: 'column', gap: '18px', zIndex: '20' }); }
});
$$('.main-nav a').forEach(a => a.addEventListener('click', () => { const n = $('.main-nav'); if (window.innerWidth <= 900) n.removeAttribute('style'); }));

