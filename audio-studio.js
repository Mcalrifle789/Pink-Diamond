/* Pink Diamond — studio audio bar.
   Per the reference dashboard: a player with shuffle / prev / play / next /
   repeat, a seekable timeline, and a Generate button. "Sapphire Skies —
   Echoes In Blue" is the house track; playback is a generated WebAudio loop
   until real generated audio is wired to the backend. */
(function audioStudio() {
  const bar = document.getElementById('audio-bar');
  if (!bar) return;
  const $ = (id) => document.getElementById(id);
  const TRACKS = [
    { title: 'Sapphire Skies', track: 'Echoes In Blue', duration: 238, scale: [220, 261.63, 329.63, 392, 440] },
    { title: 'Rose Refraction', track: 'Facet Glow', duration: 201, scale: [246.94, 293.66, 369.99, 440] },
    { title: 'Violet Marble', track: 'Deep Cut', duration: 187, scale: [196, 233.08, 293.66, 349.23] },
    { title: 'Peach Ambient', track: 'Slow Sparkle', duration: 254, scale: [261.63, 311.13, 392, 466.16] },
  ];
  let idx = 0, playing = false, elapsed = 0, audioCtx = null, loopTimer = null, repeat = true;

  const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  function render() {
    $('audio-title').textContent = TRACKS[idx].title;
    $('audio-track').textContent = TRACKS[idx].track;
    $('audio-duration').textContent = fmt(TRACKS[idx].duration);
    $('audio-seek').value = Math.min(100, (elapsed / TRACKS[idx].duration) * 100);
    $('audio-time').textContent = fmt(elapsed);
  }

  function ensureCtx() {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
  }

  // Gentle arpeggio loop — the stand-in for real generated audio.
  function tick() {
    if (!playing) return;
    ensureCtx();
    const t0 = audioCtx.currentTime;
    const scale = TRACKS[idx].scale;
    for (let i = 0; i < 4; i++) {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.value = scale[i % scale.length] * (i === 3 ? 2 : 1);
      gain.gain.setValueAtTime(0.0001, t0 + i * 0.24);
      gain.gain.exponentialRampToValueAtTime(0.045, t0 + i * 0.24 + 0.04);
      gain.gain.exponentialRampToValueAtTime(0.0001, t0 + i * 0.24 + 0.5);
      osc.connect(gain).connect(audioCtx.destination);
      osc.start(t0 + i * 0.24); osc.stop(t0 + i * 0.24 + 0.55);
    }
    elapsed = (elapsed + 1) % TRACKS[idx].duration;
    render();
    if (elapsed === 0 && !repeat) { next(); return; }    loopTimer = setTimeout(tick, 960);
  }

  function play() { playing = true; bar.classList.add('playing'); ensureCtx(); tick(); }
  function pause() { playing = false; bar.classList.remove('playing'); clearTimeout(loopTimer); }
  function toggle() { playing ? pause() : play(); }
  function next() { idx = (idx + 1) % TRACKS.length; elapsed = 0; render(); if (playing) { pause(); play(); } }
  function prev() { idx = (idx - 1 + TRACKS.length) % TRACKS.length; elapsed = 0; render(); if (playing) { pause(); play(); } }

  bar.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-audio]');
    if (!btn) return;
    const action = btn.dataset.audio;
    if (action === 'play') toggle();
    if (action === 'next') next();
    if (action === 'prev') prev();
    if (action === 'shuffle') { idx = Math.floor(Math.random() * TRACKS.length); elapsed = 0; render(); showToastSafe('Shuffling your generated tracks.'); }
    if (action === 'repeat') { repeat = !repeat; showToastSafe(`Repeat ${repeat ? 'on' : 'off'} — ${repeat ? 'the current track loops.' : 'playback continues to the next track.'}`); }
    if (action === 'generate') {
      const name = ['Sapphire Skies', 'Rose Refraction', 'Violet Marble', 'Peach Nebula'][Math.floor(Math.random() * 4)];
      const sub = ['Echoes In Blue', 'Facet Study', 'Neon Slow Dance', 'First Light'][Math.floor(Math.random() * 4)];
      TRACKS.unshift({ title: name, track: sub, duration: 180 + Math.floor(Math.random() * 120), scale: TRACKS[0].scale });
      idx = 0; elapsed = 0; render();
      showToastSafe(`Generated “${name} — ${sub}” with Lyria Flash (−12 credits).`);
      window.PinkAds?.track('audioGenerate', { model: 'Lyria Flash' });
    }
  });
  $('audio-seek').addEventListener('input', (e) => {
    elapsed = (Number(e.target.value) / 100) * TRACKS[idx].duration;
    $('audio-time').textContent = fmt(elapsed);
  });

  // showToast lives in app.js; fall back to a quiet no-op there.
  function showToastSafe(msg) { if (typeof showToast === 'function') showToast(msg); }
  render();
})();