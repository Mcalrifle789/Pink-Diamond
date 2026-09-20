/* Pink Diamond — model catalog (image, video, and uncensored routing) */
'use strict';

const IMAGE_MODELS = [
  { tier: 'Budget / best value', note: 'Extremely low credit cost — best for volume', models: [
    ['Higgsfield Soul 2.0', 'TOP — fashion, cinematic stills, character consistency (Soul ID)'],
    ['Higgsfield Soul Cinema', 'Same family, film-grade aesthetic'],
    ['Z-Image', 'Cheapest pure generation — instant lifelike portraits'],
    ['Nano Banana 2 Lite', 'Lightweight / speed-focused, good enough for volume work'],
  ]},
  { tier: 'Mid-tier', note: 'Strong balance of quality and cost', models: [
    ['Seedream 5.0 Pro', 'Strong visual reasoning, consistent images'],
    ['Recraft V4.1', 'Photorealistic + expressive, good for design'],
    ['FLUX.2', 'Speed-optimized detail — reliable workhorse'],
    ['Grok Imagine', 'Versatile styles by xAI — good all-rounder'],
    ['GPT Image 2', 'Excellent, near-perfect text rendering'],
  ]},
  { tier: 'High-end', note: 'The strongest generators available', models: [
    ['Nano Banana Pro', 'TOP — reasoning, consistency, text, faces'],
    ['Topaz', 'Premium high-resolution upscaler'],
  ]},
];

const VIDEO_MODELS = [
  { tier: 'Budget / speed', note: 'Lowest credit cost, fast output', models: [
    ['Minimax Hailuo 2.3', 'Lowest cost among capable models — great for short-form'],
    ['Wan 2.7', 'Excellent first + end frame control, very efficient'],
    ['Grok Imagine 1.5', 'Cinematic + synchronized audio, strong value'],
    ['Kling Motion Control', 'Motion transfer (video → image/character)'],
    ['Higgsfield DOP', 'VFX + camera control for directed shots'],
  ]},
  { tier: 'Mid-tier · best value overall', note: 'The bang-for-buck sweet spot', models: [
    ['Kling 3.0', 'TOP — up to 4K, multi-shot, native audio'],
    ['Kling 3.0 Omni Edit', 'Edit existing videos with text prompts'],
    ['Gemini Omni Flash', 'Generate + edit from any input, fast multimodal'],
    ['HappyHorse', 'Alibaba’s strong ranked model'],
    ['FLUX.3 Video', 'NEW — text/image/video with synchronized audio'],
  ]},
  { tier: 'High-end / premium', note: 'Flagship quality, higher credit burn', models: [
    ['Seedance 2.0 4K', 'TOP — native 4K, cinematic'],
    ['Seedance 2.5', 'NEW — up to 30s cinematic, flagship ByteDance'],
    ['MiniMax H3', 'NEW — 2K from text/keyframes, top arena rankings'],
    ['Google Veo 3.1', 'Crystal-clear AI video with sound'],
    ['Sora 2', 'OpenAI’s most advanced — deep physics simulation'],
  ]},
];


const UNCENSORED_MODELS = [
  { tier: 'Text · uncensored', note: 'Reached only while Unfiltered Mode is on', models: [
    ['Dolphin 3.0 R1', 'Instruction-tuned with the refusal layer removed — the default unfiltered brain'],
    ['Venice Uncensored', 'Blunt, opinionated, minimal guardrail padding'],
    ['Euryale 70B', 'Long-form mature fiction and sustained roleplay'],
    ['Midnight Rose 103B', 'Dense prose, dark themes, strong character voice'],
    ['Grok (unfiltered)', 'xAI house model with the loosest public settings'],
  ]},
  { tier: 'Visual · uncensored', note: 'Open-weight checkpoints, no prompt sanitising', models: [
    ['Pony Realism', 'Adult-capable photoreal checkpoint'],
    ['FLUX.2 (open weights)', 'Self-hosted route — no endpoint policy layer'],
    ['SDXL / community LoRAs', 'Bring your own style and subject adapters'],
  ]},
];

function renderCatalog() {
  const root = document.getElementById('model-catalog');
  if (!root) return;
  const block = (title, groups) => `
    <h3 class="catalog-title">${title}</h3>
    ${groups.map(g => `
      <div class="catalog-group glass">
        <div class="catalog-tier"><strong>${g.tier}</strong><span>${g.note}</span></div>
        <ul class="catalog-list">${g.models.map(([n, d]) =>
          `<li><b>${n}</b><p>${d}</p></li>`).join('')}</ul>
      </div>`).join('')}`;
  root.innerHTML = `
    <div class="catalog-intro"><h2>A catalog cut<br /><span>from the very best.</span></h2>
    <p>Every account routes through a private, never-shown key to the strongest image and video models. Free plans switch to open-weight models automatically. Unfiltered Mode adds a third rail of uncensored models.</p></div>
    ${block('IMAGE MODELS', IMAGE_MODELS)}
    ${block('VIDEO MODELS', VIDEO_MODELS)}
    <div class="catalog-heat">
      <h3 class="catalog-title heat-title">UNCENSORED MODELS <span class="heat-tag">18+ ADD-ON</span></h3>
      <p class="catalog-heat-note">These are only routed to while <a href="#unfiltered">Unfiltered Mode</a> is enabled on a paid plan. Illegal categories stay blocked on every model here.</p>
      ${UNCENSORED_MODELS.map(g => `
        <div class="catalog-group glass heat-group">
          <div class="catalog-tier"><strong>${g.tier}</strong><span>${g.note}</span></div>
          <ul class="catalog-list">${g.models.map(([n, d]) => `<li><b>${n}</b><p>${d}</p></li>`).join('')}</ul>
        </div>`).join('')}
    </div>`;
}

document.addEventListener('DOMContentLoaded', renderCatalog);
