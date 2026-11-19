# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Renders the gateway page from its state files, so what an operator sees is
decided here and covered by tests: healthy, release refused, or no release yet.
The "Try a clip" result is filled in by app.js from /api/classify."""

from __future__ import annotations

from datetime import datetime
from html import escape


def hhmm(iso: str | None) -> str:
    return datetime.fromisoformat(iso).strftime("%H:%M UTC") if iso else "not yet"


def when(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M UTC")


def next_check(minutes: int | None) -> str:
    if minutes is None:
        return "next check when the timer runs"
    return "next check in less than a minute" if minutes < 1 else f"next check in {minutes} min"


def refusal_headline(detail: str) -> str:
    """The check that failed, in the words verify_release.sh and fetch_release.sh use."""
    for needle, headline in (("signature", "Signature check failed"), ("sha256", "Digest check failed"),
                             ("older", "Older release refused"), ("names version", "Version mismatch")):
        if needle in detail:
            return headline
    return "Release refused"


def state_of(status: dict) -> str:
    fetch, release = status["fetch"] or {}, status["release"]
    if fetch.get("status") == "rejected" and fetch.get("version") != (release or {}).get("version"):
        return "refused"
    return "healthy" if release else "no-release"


def plate(site: str, state: str) -> str:
    lamp = {"healthy": ("ok", "Model running"), "refused": ("alarm", "Release refused"),
            "no-release": ("idle", "No model yet")}[state]
    return (f'<header class="plate"><div class="id"><h1>GATEWAY <span>&middot;</span> {escape(site)}</h1>'
            '<span class="maker">AnyCompany Robotics conveyor vision</span></div>'
            '<div class="access"><span>No inbound access &middot; reached through Session Manager</span>'
            f'<span class="lamp {lamp[0]}" role="status">{lamp[1]}</span></div></header>')


def readouts(release: dict, selftest: dict | None) -> str:
    v = escape(release["version"])
    score = f'{selftest["correct"]}<small>/{selftest["total"]}</small>' if selftest else '&ndash;'
    return ('<div class="readouts">'
            f'<div class="readout"><span class="v">{v}</span><span class="k">Running release</span></div>'
            f'<div class="readout ok"><span class="v">Verified</span><span class="k">Signature of {v}</span></div>'
            f'<div class="readout"><span class="v">{score}</span><span class="k">Self-test on held-out clips</span></div>'
            '</div>')


def model_panel(status: dict, state: str, minutes: int | None) -> str:
    fetch, release, selftest = status["fetch"] or {}, status["release"], status["selftest"]
    checked = hhmm(fetch.get("checked_at"))
    if state == "no-release":
        outcome = "the release bucket could not be read" if fetch.get("status") == "error" else "nothing approved yet"
        return ('<section class="panel" aria-labelledby="m-h"><h2 id="m-h">Installed model</h2>'
                '<div class="waiting"><strong>No release yet</strong><p>Waiting for the first approved model. '
                'Each new release is installed only after its signature checks out.</p></div>'
                f'<dl class="facts"><dt>Last check</dt><dd>{checked} &middot; {outcome}</dd>'
                f'<dt>Next check</dt><dd>{next_check(minutes).removeprefix("next check ")}</dd></dl></section>')
    parts = []
    if state == "refused":
        refused = escape(fetch["version"])
        running = (f'<b>{escape(release["version"])}</b> is still running and classifying clips.' if release
                   else 'No model is installed, so clips cannot be classified.')
        parts.append('<div class="alarm" role="alert"><div class="alarm-body">'
                     f'<strong>{refusal_headline(fetch.get("detail", ""))}</strong>'
                     f'<p>Release <b>{refused}</b> was refused and not installed. {running}</p>'
                     '</div></div>')
        checked = f"{checked}, {refused} refused"
    if release:
        # A self-test of an earlier release says nothing about this one.
        selftest = selftest if selftest and selftest.get("version") == release["version"] else None
        parts.append(readouts(release, selftest))
        latency = (f'<span class="mono">{selftest["mean_latency_ms"]:.0f} ms</span> per clip on this gateway&rsquo;s CPU'
                   if selftest else 'measured after the self-test')
        parts.append(f'<dl class="facts"><dt>Released</dt><dd>{when(release["released_at"])}, approved in the model registry</dd>'
                     f'<dt>Last check</dt><dd>{checked} &middot; {next_check(minutes)}</dd>'
                     f'<dt>Mean latency</dt><dd>{latency}</dd></dl>')
    if state == "refused":
        keeps = f'keeps running {escape(release["version"])}' if release else 'stays without a model'
        parts.append(f'<p class="next"><b>What to do:</b> ask the ML team to check release {escape(fetch["version"])} '
                     f'in the model registry and the release bucket. The gateway {keeps} and checks again at the '
                     'next interval.</p>')
    alarmed = " alarmed" if state == "refused" else ""
    return (f'<section class="panel{alarmed}" aria-labelledby="m-h"><h2 id="m-h">Installed model</h2>'
            + "".join(parts) + '</section>')


def try_panel(has_model: bool, max_mb: int) -> str:
    if not has_model:
        return ('<section class="panel" aria-labelledby="t-h"><h2 id="t-h">Try a clip</h2>'
                '<div class="picker"><div class="drop"><span class="hint">Classifying needs an installed model.</span></div>'
                '<button class="btn" type="button" disabled>Classify</button></div>'
                '<p class="idle-note">Try a clip becomes available once the first release is installed.</p></section>')
    return ('<section class="panel" aria-labelledby="t-h"><h2 id="t-h">Try a clip</h2>'
            '<div class="picker"><div class="drop" id="drop">'
            '<span id="pick-text">Drop a clip from this site or <label for="clip">choose a file</label></span>'
            '<span class="file" id="pick-name" hidden></span><span class="hint" id="pick-meta" hidden></span>'
            '<input id="clip" class="visually-hidden" type="file" accept="video/mp4"></div>'
            '<button class="btn" type="button" id="classify" disabled>Classify</button></div>'
            '<div id="outcome"><p class="idle-note">The installed model labels the clip as normal, jam, drop or empty, '
            f'and shows its confidence and latency. MP4 up to {max_mb} MB. The clip never leaves this gateway.</p></div>'
            '</section>')


def render(status: dict, site: str, minutes: int | None, max_mb: int) -> str:
    state = state_of(status)
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>Gateway {escape(site)}</title><link rel="stylesheet" href="/tokens.css">'
            '<link rel="stylesheet" href="/gateway.css"><script src="/app.js" defer></script></head>'
            f'<body data-state="{state}">{plate(site, state)}<main class="board">'
            f'{model_panel(status, state, minutes)}{try_panel(status["release"] is not None, max_mb)}'
            '</main></body></html>')
