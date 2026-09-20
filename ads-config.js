/* ============================================================
   Pink Diamond — advertising configuration
   ------------------------------------------------------------
   Everything an ad-ops owner needs to touch lives in this file.
   Replace the XXXX placeholders with the real IDs before launch;
   until then the site serves house creatives in the same slots,
   so layout and rotation behave identically in staging.
   ============================================================ */
'use strict';

window.ADS_CONFIG = {
  /* ---- Google identifiers ---------------------------------- */
  gtmId:       'GTM-XXXXXXX',     // Google Tag Manager container
  googleAdsId: 'AW-XXXXXXXXXX',   // Google Ads conversion tag
  ga4Id:       'G-XXXXXXXXXX',    // GA4 property (optional)

  /* ---- Google Ad Manager / Publisher Tag ------------------- */
  useGpt: true,
  networkCode: '/0000000/pink-diamond',   // GAM network + ad unit root

  /* ---- Conversion labels (Google Ads) --------------------- */
  conversions: {
    signup:           'AW-XXXXXXXXXX/signupLabelXXXX',
    subscribe:        'AW-XXXXXXXXXX/subLabelXXXXXXX',
    unfilteredAddon:  'AW-XXXXXXXXXX/heatLabelXXXXXX',
    creditPack:       'AW-XXXXXXXXXX/credLabelXXXXXX',
  },

  /* ---- Rate card ------------------------------------------
     Priced per the Pink Diamond monetization spec.            */
  rateCard: [
    { id: 'rail-left',   label: 'Vertical — left rail',   size: '160×600', price: 400, kind: 'rotating' },
    { id: 'rail-right',  label: 'Vertical — right rail',  size: '160×600', price: 400, kind: 'rotating' },
    { id: 'leaderboard', label: 'Horizontal — bottom',    size: '728×90',  price: 350, kind: 'rotating' },
    { id: 'popup',       label: 'Pop-up — dismissible',   size: '320×260', price: null, kind: 'popup' },
  ],

  /* ---- Placements -----------------------------------------
     `black` = persistent rotating slot (appears, stays, rotates
               to the next ad in sequence)
     `grey`  = pop-up slot, dismissible via the × control      */
  placements: {
    'rail-left':   { box: 'black', gptPath: '/rail-left-160x600',  sizes: [[160, 600]], rotateMs: 12000, startAt: 0 },
    'rail-right':  { box: 'black', gptPath: '/rail-right-160x600', sizes: [[160, 600]], rotateMs: 15000, startAt: 2 },
    'leaderboard': { box: 'black', gptPath: '/bottom-728x90',      sizes: [[728, 90], [970, 90]], rotateMs: 10000 },
    'popup-a':     { box: 'grey',  gptPath: '/popup-320x260',      sizes: [[320, 260]], delayMs: 18000 },
    'popup-b':     { box: 'grey',  gptPath: '/popup-320x260',      sizes: [[320, 260]], scrollDepth: 0.55 },
  },

  /* ---- Pop-up frequency capping --------------------------- */
  popupCap: { perSession: 2, minGapMs: 90000, dismissedForHours: 12 },

  /* ---- House creatives -----------------------------------
     Served in every black/grey box until Google Ads fills it.
     Rotation walks this list in sequence, then loops.         */
  houseCreatives: {
    vertical: [
      { kicker: 'SPONSORED', title: 'Cut deeper.',        body: 'Premium studio gear for people who ship.',   cta: 'See the kit' },
      { kicker: 'SPONSORED', title: 'Ship at 3am.',       body: 'Cloud GPUs by the minute. No contracts.',     cta: 'Spin one up' },
      { kicker: 'SPONSORED', title: 'Own your archive.',  body: 'Encrypted storage for generated work.',       cta: 'Claim 1 TB' },
      { kicker: 'SPONSORED', title: 'Sound, handled.',    body: 'Licensed audio for every render you make.',   cta: 'Browse library' },
    ],
    horizontal: [
      { kicker: 'SPONSORED', title: 'Your ad rotates here.', body: 'Bottom rail · 728×90 · $350 / month.',     cta: 'Book the slot' },
      { kicker: 'SPONSORED', title: 'Reach the makers.',     body: 'Creators who render daily, not weekly.',   cta: 'Get the media kit' },
      { kicker: 'SPONSORED', title: 'Launch louder.',        body: 'One horizontal placement. Full attention.', cta: 'Reserve' },
    ],
    popup: [
      { kicker: 'POP-UP / SPONSORED', title: 'One more thing.',   body: 'A tool worth the interruption — dismiss any time.', cta: 'Take a look' },
      { kicker: 'POP-UP / SPONSORED', title: 'Made for renders.', body: 'Colour-accurate displays, creator pricing.',        cta: 'See offer' },
    ],
  },
};
