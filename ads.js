/* ============================================================
   Pink Diamond — ad delivery runtime
   ------------------------------------------------------------
   Layout, per the monetization spec:
     · two vertical side placements ($400 each)
     · one horizontal bottom placement ($350)
     · black boxes  -> ads appear, stay, and rotate in sequence
     · grey boxes   -> pop-up ads, dismissible via ×
   All paid inventory is served by Google Ads (GPT). House
   creatives fill the same boxes until real slot IDs are set.
   ============================================================ */
'use strict';

(function () {
  const C = window.ADS_CONFIG || {};
  const P = C.placements || {};
  const H = C.houseCreatives || {};
  const cap = C.popupCap || { perSession: 2, minGapMs: 60000, dismissedForHours: 12 };

  const liveGpt = !!(C.useGpt && C.networkCode && !/^\/0000/.test(C.networkCode));
  const liveAds = !!(C.googleAdsId && !/^AW-XXXX/.test(C.googleAdsId));

  const ss = {
    get: (k, d) => { try { return JSON.parse(sessionStorage.getItem(k)) ?? d; } catch { return d; } },
    set: (k, v) => { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch {} },
  };
  const ls = {
    get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
    set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  };

  /* ---------- conversion tracking ---------- */
  function track(event, params) {
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push(Object.assign({ event: 'pd_' + event }, params || {}));
    const label = (C.conversions || {})[event];
    if (liveAds && label && typeof window.gtag === 'function') {
      window.gtag('event', 'conversion', Object.assign({ send_to: label }, params || {}));
    }
  }

  /* ---------- creative rendering ---------- */
  function creativeMarkup(c, shape) {
    return '<span class="ad-kicker">' + c.kicker + '</span>' +
           '<strong class="ad-title">' + c.title + '</strong>' +
           '<p class="ad-body">' + c.body + '</p>' +
           '<span class="ad-cta">' + c.cta + ' <i>↗</i></span>' +
           '<span class="ad-served">google ads · ' + shape + '</span>';
  }

  /* Black box: the ad appears, stays, then rotates to the next in sequence. */
  function startRotation(box, list, shape, rotateMs, startAt) {
    if (!box || !list || !list.length) return;
    let i = startAt || 0;
    const paint = () => {
      if (box.classList.contains('ad-hold')) return;   // don't swap under the cursor
      box.classList.remove('ad-in');
      box.innerHTML = creativeMarkup(list[i % list.length], shape);
      void box.offsetWidth;                            // restart the entry animation
      box.classList.add('ad-in');
      i++;
    };
    paint();
    if (list.length > 1) {
      const timer = setInterval(() => { if (!document.hidden) paint(); }, rotateMs || 12000);
      box.dataset.rotating = 'on';
      box.addEventListener('mouseenter', () => box.classList.add('ad-hold'));
      box.addEventListener('mouseleave', () => box.classList.remove('ad-hold'));
      window.addEventListener('pagehide', () => clearInterval(timer));
    }
    box.addEventListener('click', () => {
      track('adClick', { placement: box.dataset.placement });
      if (window.showToast) window.showToast('Ad clicked — this inventory is sold through Google Ads.');
    });
  }

  /* Real GPT slot when the network code is set; house creative otherwise. */
  function fillBox(box) {
    const key = box.dataset.placement;
    const conf = P[key] || {};
    const shape = /rail/.test(key) ? '160×600' : (/leader/.test(key) ? '728×90' : '320×260');
    if (liveGpt) {
      const id = 'gpt-' + key;
      box.innerHTML = '<div id="' + id + '"></div>';
      window.googletag = window.googletag || { cmd: [] };
      window.googletag.cmd.push(function () {
        const slot = window.googletag
          .defineSlot(C.networkCode + conf.gptPath, conf.sizes, id)
          .addService(window.googletag.pubads());
        window.googletag.pubads().enableSingleRequest();
        window.googletag.pubads().collapseEmptyDivs(false);
        window.googletag.enableServices();
        window.googletag.display(id);
        // Live slots rotate by refreshing on the same cadence as the house loop.
        if (conf.rotateMs) setInterval(() => {
          if (!document.hidden) window.googletag.pubads().refresh([slot]);
        }, conf.rotateMs);
      });
      return;
    }
    const list = /rail/.test(key) ? H.vertical : (/leader/.test(key) ? H.horizontal : H.popup);
    startRotation(box, list, shape, conf.rotateMs, conf.startAt);
  }

  document.querySelectorAll('.ad-box-black[data-placement]').forEach(fillBox);

  /* ---------- grey boxes: dismissible pop-up ads ---------- */
  let shown = ss.get('pk_ads_popup_shown', 0);
  let lastShown = 0;

  const suppressed = () => Date.now() < ls.get('pk_ads_popup_off', 0);

  function buildPopup(key, creative, shape) {
    const el = document.createElement('div');
    el.className = 'ad-popup ad-box-grey';
    el.dataset.placement = key;
    el.setAttribute('role', 'complementary');
    el.setAttribute('aria-label', 'Advertisement');
    el.innerHTML =
      '<button class="ad-popup-close" aria-label="Dismiss ad">×</button>' +
      '<div class="ad-popup-inner">' + creativeMarkup(creative, shape) + '</div>';
    el.querySelector('.ad-popup-close').addEventListener('click', e => {
      e.stopPropagation();
      el.classList.remove('open');
      track('adDismiss', { placement: key });
      setTimeout(() => el.remove(), 340);
      ls.set('pk_ads_popup_off', Date.now() + (cap.dismissedForHours || 12) * 36e5);
    });
    el.querySelector('.ad-popup-inner').addEventListener('click', () => {
      track('adClick', { placement: key });
      if (window.showToast) window.showToast('Ad clicked — pop-up inventory is served via Google Ads.');
    });
    document.body.appendChild(el);
    requestAnimationFrame(() => el.classList.add('open'));
    return el;
  }

  function showPopup(key) {
    if (suppressed()) return;
    if (shown >= (cap.perSession || 2)) return;
    if (Date.now() - lastShown < (cap.minGapMs || 60000)) return;
    if (document.querySelector('.agent-overlay.open')) return;    // never over the agent
    if (document.querySelector('.modal-backdrop.open')) return;    // never over a modal
    const list = H.popup || [];
    if (!list.length) return;
    buildPopup(key, list[shown % list.length], '320×260');
    shown++; lastShown = Date.now();
    ss.set('pk_ads_popup_shown', shown);
    track('adImpression', { placement: key, format: 'popup' });
  }

  Object.entries(P).forEach(([key, conf]) => {
    if (conf.box !== 'grey') return;
    if (conf.delayMs) setTimeout(() => showPopup(key), conf.delayMs);
    if (conf.scrollDepth) {
      const onScroll = () => {
        const max = document.body.scrollHeight - window.innerHeight;
        if (max > 0 && window.scrollY / max >= conf.scrollDepth) {
          window.removeEventListener('scroll', onScroll);
          showPopup(key);
        }
      };
      window.addEventListener('scroll', onScroll, { passive: true });
    }
  });

  /* ---------- rate card (advertise section) ---------- */
  const rateRoot = document.getElementById('rate-card');
  if (rateRoot && Array.isArray(C.rateCard)) {
    rateRoot.innerHTML = C.rateCard.map(r =>
      '<div class="rate-row">' +
        '<span class="rate-box ' + (r.kind === 'popup' ? 'is-grey' : 'is-black') + '"></span>' +
        '<div class="rate-meta"><strong>' + r.label + '</strong>' +
        '<span>' + r.size + ' · ' + (r.kind === 'popup' ? 'dismissible pop-up' : 'rotates in sequence') + '</span></div>' +
        '<b class="rate-price">' + (r.price === null ? 'on request' : '$' + r.price + '<i>/mo</i>') + '</b>' +
      '</div>').join('');
  }

  /* impressions for the persistent rails */
  document.querySelectorAll('.ad-box-black[data-placement]').forEach(box => {
    track('adImpression', { placement: box.dataset.placement, format: 'rotating' });
  });

  window.PinkAds = { track, showPopup, liveGpt, liveAds };
})();
