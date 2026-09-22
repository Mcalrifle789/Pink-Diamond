/* Pink Diamond — continuous vortex background.
   A slow swirl of rose particles behind the landing and agent surfaces,
   inspired by the PowerPoint vortex transition. 60fps target, single canvas,
   pauses entirely under prefers-reduced-motion. */
(function vortexBackground() {
  const canvas = document.getElementById('vortex-bg');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const DPR = Math.min(devicePixelRatio || 1, 2);
  let W = 0, H = 0;
  function resize() {
    W = canvas.width = innerWidth * DPR;
    H = canvas.height = innerHeight * DPR;
    canvas.style.width = innerWidth + 'px';
    canvas.style.height = innerHeight + 'px';
  }
  addEventListener('resize', resize); resize();

  // Particles orbit the viewport centre-left, drifting inward — a slow vortex.
  const COUNT = Math.min(Math.round(innerWidth / 22), 90);
  const particles = Array.from({ length: COUNT }, () => spawn());

  function spawn() {
    return {
      a: Math.random() * Math.PI * 2,                       // orbit angle
      r: 120 + Math.random() * Math.max(W, H) * 0.55,       // orbit radius
      speed: (0.05 + Math.random() * 0.12) * (Math.random() < 0.5 ? 1 : -1) * DPR,
      drift: (Math.random() - 0.5) * 0.06 * DPR,            // inward/outward drift
      size: 0.6 + Math.random() * 1.9,
      hue: 292 + Math.random() * 24,                        // pink/magenta range
      alpha: 0.10 + Math.random() * 0.35,
    };
  }

  let lastT = performance.now();
  function frame(t) {
    const dt = Math.min((t - lastT) / 1000, 0.05); lastT = t;
    ctx.clearRect(0, 0, W, H);
    const cx = W * 0.5, cy = H * 0.46;
    for (const p of particles) {
      p.a += p.speed * dt;
      p.r += p.drift;
      if (p.r < 90 * DPR || p.r > Math.max(W, H) * 0.8) { Object.assign(p, spawn()); continue; }
      const x = cx + Math.cos(p.a) * p.r;
      const y = cy + Math.sin(p.a) * p.r * 0.62;            // slight elliptical swirl
      ctx.beginPath();
      ctx.arc(x, y, p.size * DPR, 0, Math.PI * 2);
      ctx.fillStyle = `hsla(${p.hue}, 88%, 72%, ${p.alpha})`;
      ctx.fill();
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();