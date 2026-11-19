// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
//
// "Try a clip": sends the chosen MP4 to /api/classify and draws the verdict, or
// says why the clip was not classified. The rest of the page is server-rendered.
'use strict';

let chosen = null;
const $ = (id) => document.getElementById(id);

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

const pct = (p) => `${(p * 100).toFixed(1)} %`;
const mb = (bytes) => `${Math.max(0.1, bytes / 1048576).toFixed(1)} MB`;

function choose(file) {
  if (!file) return;
  chosen = file;
  $('pick-text').hidden = true;
  $('pick-name').hidden = false;
  $('pick-name').textContent = file.name;
  $('pick-meta').hidden = false;
  $('pick-meta').replaceChildren(`${mb(file.size)} · `);
  const change = el('label', null, 'change');
  change.htmlFor = 'clip';
  $('pick-meta').append(change);  // nosemgrep: jquery-insecure-method - $ is document.getElementById and Element.append inserts nodes and text, never HTML
  $('classify').disabled = false;
}

function classified(r) {
  const result = el('div', 'result');
  const fig = el('figure', 'frame-wrap');
  const frame = el('div', 'frame');
  const img = el('img');
  img.src = r.frame;
  img.alt = `First frame of ${chosen.name}`;
  frame.append(img);
  fig.append(frame, el('figcaption', 'frame-cap', 'First frame of the clip'));
  const verdict = el('div', 'verdict');
  const label = el('p', 'label');
  const conf = el('span', null, pct(r.confidence));
  conf.append(el('small', null, 'confidence'));
  label.append(el('b', null, r.label), conf);
  const scores = el('ul', 'scores');
  scores.setAttribute('aria-label', 'Score for each label');
  for (const [name, p] of Object.entries(r.probabilities).sort((a, b) => b[1] - a[1])) {
    const li = el('li', name === r.label ? 'top' : null);
    const bar = el('progress');
    Object.assign(bar, { max: 100, value: p * 100 });
    bar.setAttribute('aria-label', `${name} ${pct(p)}`);
    li.append(el('span', 'n', name), bar, el('span', 'p', pct(p)));
    scores.append(li);
  }
  verdict.append(label, scores);
  result.append(fig, verdict);
  const stamp = el('p', 'stamp');
  const lat = el('span', null, 'Latency ');
  lat.append(el('span', 'mono', `${Math.round(r.latency_ms)} ms`));
  const model = el('span', null, 'Model ');
  model.append(el('span', 'mono', r.model));
  stamp.append(lat, model, el('span', 'local', 'The clip never leaves this gateway.'));
  return [result, stamp];
}

function refused(reason) {
  const box = el('div', 'reject');
  box.setAttribute('role', 'alert');
  const glyph = el('span', 'glyph', '✕');
  glyph.setAttribute('aria-hidden', 'true');
  const body = el('div');
  body.append(el('strong', null, `Clip not classified: ${reason}`));
  const detail = el('p');
  detail.append(el('span', 'mono', chosen.name), ' failed the same video checks the cloud validation runs. Use an MP4 clip (H.264, H.265, VP9 or MPEG-4) of at most 50 MB recorded on this line.');
  body.append(detail, el('p', 'idle-note', 'Nothing was sent anywhere.'));
  box.append(glyph, body);
  return [box];
}

async function classify() {
  $('classify').disabled = true;
  $('outcome').replaceChildren(el('p', 'idle-note', 'Classifying…'));
  try {
    const response = await fetch('/api/classify', { method: 'POST', headers: { 'Content-Type': 'video/mp4' }, body: chosen });
    const r = await response.json();
    $('outcome').replaceChildren(...(response.ok ? classified(r) : refused(r.error)));
  } catch (err) {
    $('outcome').replaceChildren(...refused(err.message));
  }
  $('classify').disabled = false;
}

function wire() {
  const zone = $('drop');
  if (!zone) return;  // no installed model
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('over'));
  zone.addEventListener('drop', (e) => { e.preventDefault(); zone.classList.remove('over'); choose(e.dataTransfer.files[0]); });
  $('clip').addEventListener('change', (e) => choose(e.target.files[0]));
  $('classify').addEventListener('click', classify);
}

wire();
