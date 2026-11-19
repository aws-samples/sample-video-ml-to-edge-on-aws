// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
//
// web/uploads.js against a minimal DOM, a controllable status API and manual timers.
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const SOURCE = fs.readFileSync(path.join(__dirname, '..', '..', 'web', 'uploads.js'), 'utf8');
const CLIP = 'c'.repeat(32);

function node(tag) {
  return {
    tag, className: '', textContent: '', children: [],
    append(...nodes) { this.children.push(...nodes); },
    setAttribute() {},
  };
}

const text = (n) => [n.textContent, ...n.children.map(text)].join(' ').replace(/\s+/g, ' ').trim();

function portal() {
  const list = node('ul');
  list.children = [node('li')];
  Object.defineProperty(list, 'firstElementChild', { get: () => list.children[0] });
  list.replaceChildren = (...nodes) => { list.children = nodes; };
  const timers = [];
  const answers = [];
  const store = {};
  const clock = { now: Date.parse('2026-10-15T14:36:20Z') };
  class FakeDate extends Date {
    static now() { return clock.now; }
  }
  const context = {
    document: { getElementById: () => list, createElement: node },
    localStorage: { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } },
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    clearTimeout: (id) => { if (id) timers[id - 1] = null; },
    Date: FakeDate,
  };
  const Uploads = vm.runInNewContext(`${SOURCE}\nUploads;`, context);
  // Each poll gets a pending answer; reply() settles the oldest one.
  const fetchUploads = () => new Promise((resolve) => answers.push(resolve));
  const settle = () => new Promise((resolve) => setImmediate(resolve));
  return {
    Uploads, fetchUploads, clock,
    rows: () => list.children.slice(1).map(text),
    async reply(uploads) { answers.shift()(uploads); await settle(); },
    pending: () => answers.length,
    stored: (k) => store[k],
    // Runs the scheduled polls and returns their delay in ms, or 0 if none was scheduled.
    tick() {
      const due = timers.splice(0).filter(Boolean);
      due.forEach((t) => t.fn());
      return due.length ? due[0].ms : 0;
    },
  };
}

const listed = (state) => [{ clip: CLIP, label: 'jam', uploaded: '2026-10-15T14:36:20+00:00', state }];

test('a just-uploaded clip shows scanning, then validating, then accepted', async () => {
  const p = portal();
  p.Uploads.start('me', p.fetchUploads);
  await p.reply([]);

  const entry = p.Uploads.add('jam-002.mp4', 'jam', 'queued');
  p.Uploads.update(entry, { state: 'uploading', percent: 100 });
  p.Uploads.update(entry, { state: 'scanning', clip: CLIP });
  // The status API is still answering; the row already says what is true.
  assert.equal(p.pending(), 1);
  assert.match(p.rows()[0], /^jam-002\.mp4 jam .* Scanning malware check$/);

  // The first answer does not list the clip yet: the row stays and polling goes on.
  await p.reply([]);
  assert.match(p.rows()[0], /Scanning malware check$/);
  assert.ok(p.tick(), 'a poll is scheduled while the clip is not listed');

  await p.reply(listed('validating'));
  assert.deepEqual(p.rows().length, 1);
  assert.match(p.rows()[0], /^jam-002\.mp4 jam .* Validating checking the video stream$/);
  assert.ok(p.tick(), 'a poll is scheduled while the clip is validating');

  await p.reply(listed('accepted'));
  assert.match(p.rows()[0], /^jam-002\.mp4 jam .* Accepted added to the training pool$/);
  assert.equal(p.tick(), 0, 'polling stops once every clip is final');
});

test('a slow answer to an older poll never starts a second polling loop', async () => {
  const p = portal();
  p.Uploads.start('me', p.fetchUploads);
  const entry = p.Uploads.add('drop-002.mp4', 'drop', 'queued');
  p.Uploads.update(entry, { state: 'scanning', clip: CLIP });
  await p.reply([]);
  p.tick();
  await p.reply([]);
  p.tick();
  assert.equal(p.pending(), 1);
});

test('a clip the status API never lists stops the fast poll after two minutes', async () => {
  const p = portal();
  p.Uploads.start('me', p.fetchUploads);
  await p.reply([]);
  const entry = p.Uploads.add('normal-002.mp4', 'normal', 'queued');
  p.Uploads.update(entry, { state: 'scanning', clip: CLIP });
  await p.reply([]);
  assert.equal(p.tick(), 1000);

  p.clock.now += 121000;
  await p.reply([]);
  assert.match(p.rows()[0], /^normal-002\.mp4 normal .* Status unavailable retrying$/);
  assert.equal(p.tick(), 15000);

  // A late listing still takes over the row.
  await p.reply(listed('accepted'));
  assert.match(p.rows()[0], /Accepted added to the training pool$/);
  assert.equal(p.tick(), 0);
});

test('clips uploaded while earlier ones are still scanning all keep their names', async () => {
  const p = portal();
  p.Uploads.start('me', p.fetchUploads);
  await p.reply([]);
  const clips = ['1', '2', '3', '4', '5'].map((d) => d.repeat(32));
  const files = clips.map((_, i) => `normal-${i + 1}.mp4`);
  const answer = (n, state) => clips.slice(0, n).reverse()
    .map((clip) => ({ clip, label: 'normal', uploaded: '2026-10-15T14:36:20+00:00', state }));
  for (const [i, clip] of clips.entries()) {
    const entry = p.Uploads.add(files[i], 'normal', 'queued');
    p.Uploads.update(entry, { state: 'scanning', clip });
    // An earlier poll answers while this clip is on its way: it lists only the clips before it.
    if (i) await p.reply(answer(i, 'scanning'));
  }
  while (p.pending()) await p.reply(answer(clips.length, 'accepted'));
  p.tick();
  while (p.pending()) await p.reply(answer(clips.length, 'accepted'));

  assert.deepEqual(p.rows().map((r) => r.split(' ')[0]), [...files].reverse());
  assert.deepEqual(Object.values(JSON.parse(p.stored('conveyor.names.me'))).sort(), files);
});
