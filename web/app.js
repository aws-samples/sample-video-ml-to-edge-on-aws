// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
//
// Contributor portal: sign in, pick a label, add clips, upload each one straight
// to the intake bucket through a presigned PUT, and follow it in the pipeline.
'use strict';

const MAX_BYTES = 200 * 1024 * 1024;
const MEANINGS = {
  normal: 'Parts flow freely',
  jam: 'Parts pile up and stop',
  drop: 'A part falls off the belt',
  empty: 'Belt runs with no parts',
};
let config;
let session;
let chosen = [];
let busy = false;

const $ = (id) => document.getElementById(id);
const mb = (bytes) => `${Math.max(0.1, bytes / 1048576).toFixed(bytes < 10485760 ? 1 : 0)} MB`;

function showSignedIn() {
  $('signin-view').hidden = true;
  $('app-view').hidden = false;
  $('who-name').textContent = session.username;
  $('who-site').textContent = session.site;
  $('site-note').textContent = session.site;
  Uploads.start(session.sub, fetchUploads);
}

function notice(text, isError) {
  $('signin-notice').hidden = !text;
  $('signin-notice').classList.toggle('error', Boolean(isError));
  $('signin-message').textContent = text || '';
}

async function onSignIn(event) {
  event.preventDefault();
  const form = event.target;
  try {
    let result;
    if (Auth.needsNewPassword()) {
      if (form.newPassword.value !== form.repeatPassword.value) return notice('The two new passwords differ.', true);
      result = await Auth.setNewPassword(form.newPassword.value);
    } else {
      result = await Auth.signIn(form.username.value, form.password.value);
    }
    if (!result.done) {
      form.username.readOnly = true;
      $('password-row').hidden = true;
      $('new-password-row').hidden = false;
      $('repeat-password-row').hidden = false;
      $('signin-button').textContent = 'Set password and sign in';
      return notice('First sign-in: choose a new password to finish signing in.');
    }
    session = result.session;
    showSignedIn();
  } catch (err) {
    notice(`Sign-in failed: ${err.message}`, true);
  }
}

function label() {
  const checked = document.querySelector('input[name="label"]:checked');
  return checked ? checked.value : null;
}

function renderChips() {
  for (const value of config.labels) {
    const chip = document.createElement('label');
    chip.className = 'chip';
    const input = document.createElement('input');
    Object.assign(input, { type: 'radio', name: 'label', value });
    const text = document.createElement('span');
    const b = document.createElement('b');
    b.textContent = value;
    const small = document.createElement('small');
    small.textContent = MEANINGS[value] || '';
    text.append(b, small);
    chip.append(input, text);
    $('chips').append(chip);  // nosemgrep: jquery-insecure-method - $ is document.getElementById and Element.append inserts nodes and text, never HTML
  }
  $('chips').addEventListener('change', refreshButton);
}

function refreshButton() {
  const ready = chosen.filter((c) => !c.refused).length;
  const button = $('upload');
  button.disabled = busy || !ready || !label();
  if (busy) button.textContent = `Uploading ${ready} clip${ready === 1 ? '' : 's'}…`;
  else if (!label()) button.textContent = 'Choose a label';
  else if (!ready) button.textContent = 'Add clips to upload';
  else button.textContent = `Upload ${ready} clip${ready === 1 ? '' : 's'} as “${label()}”`;
}

function addFiles(files) {
  if (busy) return;
  chosen = [...files].map((file) => ({ file, refused: file.size > MAX_BYTES || !file.name.toLowerCase().endsWith('.mp4') }));
  $('files').replaceChildren(...chosen.map((c) => {
    const li = document.createElement('li');
    li.className = c.refused ? 'file refused' : 'file';
    const name = document.createElement('span');
    name.className = 'name';
    name.textContent = c.file.name;
    c.meta = document.createElement('span');
    c.meta.className = 'meta';
    c.meta.textContent = c.refused ? refusal(c.file) : `${mb(c.file.size)} · ready`;
    li.append(name, c.meta);
    c.row = li;
    return li;
  }));
  refreshButton();
}

function refusal(file) {
  return file.size > MAX_BYTES ? `too large (${mb(file.size)}, limit 200 MB)` : 'not an .mp4 file';
}

async function api(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', Authorization: session.token },
    body: body && JSON.stringify(body),
  });
  const doc = await response.json();
  if (!response.ok) throw new Error(doc.error || doc.message || `HTTP ${response.status}`);
  return doc;
}

async function fetchUploads() {
  return (await api('GET', '/api/uploads')).uploads;
}

// XMLHttpRequest because fetch reports no upload progress.
function put(grant, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', grant.url);
    for (const [name, value] of Object.entries(grant.headers)) xhr.setRequestHeader(name, value);
    xhr.upload.onprogress = (e) => onProgress(e.loaded);
    xhr.onload = () => (xhr.status === 200 ? resolve() : reject(new Error(`HTTP ${xhr.status}`)));
    xhr.onerror = () => reject(new Error('network error'));
    xhr.send(file);
  });
}

async function uploadAll() {
  busy = true;
  refreshButton();
  const lab = label();
  const work = chosen.map((c) => {
    if (c.refused) {
      Uploads.add(c.file.name, lab, 'rejected', { step: 'upload', reason: refusal(c.file) });
      return null;
    }
    const bar = document.createElement('progress');
    Object.assign(bar, { max: 100, value: 0 });
    bar.setAttribute('aria-label', `${c.file.name} upload progress`);
    c.row.append(bar);
    c.meta.textContent = 'Waiting';
    return { ...c, bar, entry: Uploads.add(c.file.name, lab, 'queued') };
  }).filter(Boolean);
  for (const w of work) {
    try {
      const grant = await api('POST', '/api/presign', { label: lab, size: w.file.size });
      await put(grant, w.file, (loaded) => {
        const pct = Math.round((100 * loaded) / w.file.size);
        w.bar.value = pct;
        w.meta.textContent = `${mb(loaded)} of ${mb(w.file.size)} · ${pct} %`;
        Uploads.update(w.entry, { state: 'uploading', percent: pct });
      });
      w.bar.value = 100;
      w.row.classList.add('done');
      w.meta.textContent = '✓ Uploaded';
      Uploads.update(w.entry, { state: 'scanning', clip: grant.clipId });
    } catch (err) {
      w.meta.textContent = `Failed: ${err.message}`;
      Uploads.update(w.entry, { state: 'rejected', step: 'upload', reason: `upload failed (${err.message})` });
    }
  }
  busy = false;
  chosen = [];
  refreshButton();
}

function wireDrop() {
  const zone = $('drop');
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('over'));
  zone.addEventListener('drop', (e) => { e.preventDefault(); zone.classList.remove('over'); addFiles(e.dataTransfer.files); });
  $('pick').addEventListener('change', (e) => addFiles(e.target.files));
}

async function start() {
  config = await (await fetch('config.json')).json();
  Auth.init(config);
  renderChips();
  wireDrop();
  $('signin').addEventListener('submit', onSignIn);
  $('upload').addEventListener('click', uploadAll);
  $('sign-out').addEventListener('click', () => { Auth.signOut(); Uploads.stop(); location.reload(); });
  session = Auth.session();
  if (session) showSignedIn();
  refreshButton();
}

start();
