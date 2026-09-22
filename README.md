# Pink Diamond

The rose facet of the Diamond family. Pink Diamond is the same web-hosted AI
agent as Pale Diamond — tasks, automation, image and video generation — with
two things Pale doesn't have:

1. **Unfiltered Mode**, a paid 18+ add-on that drops the agent's filtering.
2. **A real ad layout**, priced and wired for Google Ads.

Built with **C++, Python, and SQL**: the static front end ships as-is, a
Python (FastAPI) backend owns accounts/billing/entitlement, SQLite holds the
schema, and a C++ core implements the ad-delivery engine.

## Run it

Front end (static, no build step):

```bash
python -m http.server 4399     # or: npx serve .
# then open http://localhost:4399
```

Backend (owns accounts, Pink Mode entitlement, and the OpenRouter proxy):

```bash
pip install -r backend/requirements.txt
set OPENROUTER_API_KEY=sk-or-...        # the key stays server-side
uvicorn main:app --port 4400            # from backend/
# API docs at http://localhost:4400/docs
```

## Layout

| Path                | Role                                                            |
| ------------------- | --------------------------------------------------------------- |
| `index.html`        | The whole page: landing, plans, agent overlay, modals, ad boxes  |
| `styles.css`        | The Diamond design system, hue-shifted from pale blue to pink    |
| `pink.css`          | Pink-only additions: ad layout + Unfiltered Mode components      |
| `app.js`            | Accounts, plans, billing, profile, agent chat                    |
| `unfiltered.js`     | The paid add-on: entitlement, 18+ gate, checkout, unfiltered voice |
| `ads.js`            | Ad delivery UI: rotation, pop-ups, GPT slots, conversion tracking |
| `ads-config.js`     | **The only file ad-ops needs to touch** — IDs, rate card, creatives |
| `model-catalog.js`  | Image, video, and uncensored model catalogs                      |
| `backend/`          | FastAPI service: auth, subscriptions, Pink Mode gate, chat proxy |
| `database/`         | `schema.sql` — users, subscriptions, credits, chats, ad slots    |
| `core/`             | C++ ad engine: black-box rotation + grey pop-up policy           |
| `verify.mjs`        | Playwright smoke test, 29 checks over both features              |

## Unfiltered Mode

The product differentiator. Off by default; the agent behaves exactly like Pale
Diamond. Turning it on requires all four of these, in order:

1. a signed-in account,
2. a **paid** plan — Free is refused and sent to the plan grid,
3. a one-time 18+ confirmation (`#adult-modal`),
4. the add-on purchase (`#addon-modal`).

Once on: tone goes blunt, adult and explicit creative work is allowed, routing
moves to uncensored open-weight models, and each message costs **2 credits
instead of 1**. Toggling it off is instant and stops the charge at the end of
the period.

**The entitlement is enforced server-side.** `backend/main.py` re-checks the
`pink_mode` subscription on every chat request and picks the model itself —
the browser toggle is advisory, so a forged `unfiltered: true` in localStorage
buys nothing. The 2× credit charge and the uncensored model routing both
happen inside the API that holds the OpenRouter key.

### Pricing

`+$18 / month` on top of any paid plan, repriced to `$14.40` under the yearly
toggle to match the 20% yearly saving on plans. So `Plus $22.99 + $18 = $40.99/mo`.
Change `HEAT.price` in `unfiltered.js` and `PINK_MODE_PRICE_CENTS` in
`backend/main.py` together.

### What stays blocked at every tier

Sexual content involving minors, sexual imagery of real people, and genuine
weapon, drug-synthesis or malware instruction. No subscription unlocks these;
the 18+ gate states it, the landing section states it, and the backend system
prompt repeats it on every request — paid or not.

## Ad layout

Priced per the monetization spec:

| Placement                 | Box   | Size    | Price     | Behaviour                                |
| ------------------------- | ----- | ------- | --------- | ---------------------------------------- |
| Vertical — left rail      | black | 160×600 | $400 / mo | appears, stays, rotates in sequence      |
| Vertical — right rail     | black | 160×600 | $400 / mo | same, offset two creatives in the loop   |
| Horizontal — bottom       | black | 728×90  | $350 / mo | sticky, rotates on a 10s cadence         |
| Pop-up                    | grey  | 320×260 | on request| dismissible with `×`                     |

**Black boxes** are persistent — no close control, by design. **Grey boxes** are
the pop-ups; the `×` dismisses them and suppresses further pop-ups for 12 hours.
Pop-ups are capped at 2 per session with a 90s minimum gap, never open over the
agent or a modal, and all ad surfaces fade out while the agent is open.

Rails are hidden below 1280px; the bottom unit stays at every width.

### Core engine (C++)

`core/ad_engine.cpp` is the source of truth for those rules: black-box rotation
in sequence, and the grey pop-up policy (2 per session, 90s gap, 12h suppression
after dismissal). Build it with CMake:

```bash
cmake -S core -B core/build
cmake --build core/build          # produces pd_ad_engine.dll + a CLI smoke test
```

`backend/ad_engine.py` loads the shared library when built and falls back to an
identical pure-Python implementation otherwise (rotation, cap, gap, and
suppression all verified against the spec).

### Going live with Google Ads

Everything is stubbed with house creatives until you fill in `ads-config.js`:

```js
gtmId:       'GTM-XXXXXXX',            // Google Tag Manager container
googleAdsId: 'AW-XXXXXXXXXX',          // Google Ads conversion tag
ga4Id:       'G-XXXXXXXXXX',           // GA4 property
networkCode: '/0000000/pink-diamond',  // Google Ad Manager network + unit root
```

The moment a value stops matching its `XXXX` placeholder, the corresponding tag
loads for real: GTM and gtag.js from `index.html`, and GPT slot definitions from
`ads.js`, which then serves the real inventory instead of house creatives.

### Conversions tracked

`signup`, `subscribe`, `unfilteredAddon`, `creditPack`, plus `adImpression`,
`adClick` and `adDismiss`. Each one pushes to `dataLayer` unconditionally (so GTM
sees it) and fires a Google Ads conversion when a matching label exists in
`ads-config.js → conversions`.

## Off-site campaigns

TikTok, Instagram, Reddit and YouTube campaign structure, creative concepts and
budgets are specified in [`ADVERTISING.md`](./ADVERTISING.md). Those are ready to
execute but not executed — launching them needs ad-account access and a budget
decision.

## Tests

```bash
python -m http.server 4399 &
node verify.mjs
```

29 checks: rail and leaderboard rendering, rotation, the rate card, the full
four-step Unfiltered funnel, price maths, the unfiltered agent voice, pop-up
dismissal, mobile layout, and a zero-console-error assertion.

`verify.mjs` points at a Playwright install and a Chromium binary by absolute
path — adjust the two constants at the top for another machine.

Backend: `python -m py_compile backend/*.py` passes; the ad-engine policy suite
(rotation, cap, gap, suppression) runs green in the pure-Python path.

## Before launch

- Wire real Stripe billing; `unfiltered` is a subscription row in SQLite once
  `POST /api/subscribe/pink-mode` exists, but no real money moves yet.
- Set `PD_SESSION_SECRET` and `OPENROUTER_API_KEY` in the backend environment.
- Verify age properly if you operate where that is required; a checkbox is not
  age verification.
- Fill in the four Google IDs and book the three ad slots.

## Spec update (Sep 2026 — reference images + prompt/spec docs)

The D:\VERCEL\PRIVATE VERCEL\PINK DIAMOND reference set (three UI mocks, the
logo, and the handwritten prompt + product spec) is now implemented:

- **Pricing** — Free (open-weight models), **Go $11.99, Plus $22.99, Pro
  $33.99, Max $121.99** (handwritten prompt + product spec; the pricing mock's
  Standard/Plus/Max figures disagree and were used for visuals only).
- **Ten themes** — full re-tint palettes (Neon Rose default, Blush Porcelain,
  Candlelight Peach, Coral Dawn, Midnight Bloom, Obsidian, Amethyst Haze,
  Emerald Facet, Sapphire Facet, Ultraviolet). Saved per account locally and
  via `PUT /api/theme` when the API origin is configured (`window.PINK_API`),
  restored on sign-in.
- **Personal API-key funding (50%)** — half of every plan payment and credit
  pack funds the account's private key balance (`users.api_balance`,
  `native/rust/pink-ledger` is the executable spec). Low/zero-balance notices
  are first-class: inline agent notices plus `notice` in `/api/chat`.
- **Audio generation** — `AUDIO_MODELS` in the catalog and a studio player bar
  (shuffle / prev / play / next / repeat / seek / Generate) matching the
  dashboard reference; WebAudio house tracks until real generation is wired.
- **Continuous vortex background** — `vortex.js`, a slow rose particle swirl
  on a single canvas, paused under reduced-motion.
- **Scroll-pulsing diamond** — continuous rotation with a scroll-driven pulse
  in scale and glow (degrades to scroll-only rotation under reduced motion).
- **Native stubs per the language directive** — Rust funding ledger
  (`native/rust/pink-ledger`, `cargo test`), C vortex kernel
  (`native/c/vortex.c`), Swift `PinkDiamondKit.swift`, ObjC++ bridge.
  The Omaris compiler was not found on this machine (`where.exe /R D:\`
  found no match) — drop the toolchain path in and a starter `.omaris`
  module can be added.

Smoke test: `node verify.mjs` — 29/29 green after the update, including the
repriced add-on checkout and a zero-console-error pass.
