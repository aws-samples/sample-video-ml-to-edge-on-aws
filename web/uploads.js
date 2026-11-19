// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
//
// "Your recent uploads": the caller's newest clips in their site, from /api/uploads,
// with where each one is in the pipeline, plus the clips this page is uploading.
// Clip names never leave the browser; it keeps a clip-id-to-name map for display.
'use strict';

const Uploads = (() => {
  // A clip spends a few seconds each in scanning and validating; a slower poll misses them.
  const POLL_MS = 1000;
  // Bounds the fast poll: a clip the status API does not list within LISTING_WAIT_MS
  // (outside the newest it reads, say) is shown as unavailable and polled slowly.
  const LISTING_WAIT_MS = 120000;
  const SLOW_POLL_MS = 15000;
  const OPEN = new Set(['scanning', 'validating', 'unknown']);
  // [track cells, word, detail]; a cell is '', 'done', 'now' or 'stop'.
  const VIEW = {
    queued: [['', '', '', ''], 'Uploading', 'queued'],
    uploading: [['now', '', '', ''], 'Uploading', ''],
    scanning: [['done', 'now', '', ''], 'Scanning', 'malware check'],
    validating: [['done', 'done', 'now', ''], 'Validating', 'checking the video stream'],
    accepted: [['done', 'done', 'done', 'done'], 'Accepted', 'added to the training pool'],
    unknown: [['', '', '', ''], 'Status unavailable', 'retrying'],
  };
  const STOP_AT = { upload: 0, scan: 1, validate: 2 };
  let key;
  let names = {};
  // Clips of this page the status API does not list yet: queued, uploading,
  // refused before upload, or uploaded and not yet in the server's answer.
  let local = [];
  let server = [];
  let timer;
  let polls = 0;
  let fetchUploads;

  function save() {
    localStorage.setItem(key, JSON.stringify(names));
  }

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function row(entry) {
    let cells; let word; let detail; let cls;
    if (entry.state === 'rejected') {
      cells = ['', '', '', ''].map((_, i) => (i < STOP_AT[entry.step] ? 'done' : i === STOP_AT[entry.step] ? 'stop' : ''));
      word = 'Rejected:'; detail = entry.reason; cls = 'is-rejected';
    } else {
      [cells, word, detail] = VIEW[entry.state];
      if (entry.state === 'uploading') detail = `${entry.percent} %`;
      cls = entry.state === 'accepted' ? 'is-accepted' : entry.state === 'unknown' ? 'is-unknown' : 'is-busy';
    }
    const li = el('li', `up ${cls}`);
    const status = el('span', 'status');
    const track = el('span', 'track');
    track.setAttribute('aria-hidden', 'true');
    for (const c of cells) track.append(el('i', c || null));
    const w = el('span', 'word', `${word} `);
    w.append(el('em', null, detail));
    status.append(track, w);
    const at = new Date(entry.uploaded);
    const when = `${at.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })} ${at.toTimeString().slice(0, 5)}`;
    li.append(el('span', 'name', entry.name), el('span', 'tag', entry.label), el('span', 'time', when), status);
    return li;
  }

  function render() {
    const list = document.getElementById('uploads');
    const head = list.firstElementChild;
    const arrived = server.map((u) => ({ ...u, name: names[u.clip] || `clip ${u.clip.slice(0, 8)}` }));
    list.replaceChildren(head, ...local.map(row), ...arrived.map(row));
  }

  function schedule(ms) {
    clearTimeout(timer);
    timer = setTimeout(poll, ms);
  }

  async function poll() {
    clearTimeout(timer);
    timer = null;
    const mine = ++polls;
    let uploads;
    try {
      uploads = await fetchUploads();
    } catch (err) {
      // A failed poll (expired token, network) is retried at the next interval.
      if (mine === polls) schedule(SLOW_POLL_MS);
      return;
    }
    // Only the newest poll renders and schedules the next one, so answers that
    // arrive out of order or late never stack up a second polling loop.
    if (mine !== polls) return;
    server = uploads;
    const listed = new Set(server.map((u) => u.clip));
    local = local.filter((e) => !listed.has(e.clip));
    // Forget the names of clips that are neither listed nor on their way.
    const kept = new Set([...listed, ...local.map((e) => e.clip)]);
    names = Object.fromEntries(Object.entries(names).filter(([clip]) => kept.has(clip)));
    const unlisted = local.filter((e) => e.clip);
    for (const e of unlisted) if (Date.now() - e.arrived > LISTING_WAIT_MS) e.state = 'unknown';
    save();
    render();
    const busy = unlisted.some((e) => e.state !== 'unknown') || server.some((u) => u.state === 'scanning' || u.state === 'validating');
    if (busy) schedule(POLL_MS);
    else if (unlisted.length || server.some((u) => OPEN.has(u.state))) schedule(SLOW_POLL_MS);
  }

  return {
    start(sub, uploadsFn) {
      key = `conveyor.names.${sub}`;
      fetchUploads = uploadsFn;
      names = JSON.parse(localStorage.getItem(key) || '{}');
      render();
      poll();
    },
    stop() { clearTimeout(timer); timer = null; },
    // Adds a clip at the top and returns it; callers update it with update().
    add(name, label, state, extra = {}) {
      const entry = { name, label, state, uploaded: new Date().toISOString(), ...extra };
      local.unshift(entry);
      render();
      return entry;
    },
    // Once a clip has arrived (it has a clip id), the server takes over its row
    // as soon as it lists it; until then the local row shows the given state.
    update(entry, changes) {
      Object.assign(entry, changes);
      render();
      if (entry.clip) {
        entry.arrived = entry.arrived || Date.now();
        names[entry.clip] = entry.name;
        save();
        poll();
      }
    },
  };
})();
