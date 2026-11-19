# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Each gateway state, rendered from the state files the fetch writes."""

from __future__ import annotations

import pytest

from conftest import ROOT, import_from

page = import_from(ROOT / "site" / "gateway", "page")
RELEASE_V3 = {"version": "v3", "released_at": "2026-10-13T13:35:32+00:00"}
SELFTEST_V3 = {"version": "v3", "accuracy": 0.9375, "correct": 15, "total": 16, "mean_latency_ms": 75.7}


def render(release=None, fetch=None, selftest=None, minutes=14):
    html = page.render({"release": release, "fetch": fetch, "selftest": selftest}, "factory-a", minutes, 50)
    return html, page.state_of({"release": release, "fetch": fetch, "selftest": selftest})


def test_healthy_shows_running_release_signature_selftest_and_next_check():
    html, state = render(RELEASE_V3, {"version": "v3", "status": "verified", "checked_at": "2026-10-13T13:36:31+00:00"}, SELFTEST_V3)
    assert state == "healthy"
    assert 'class="lamp ok" role="status">Model running' in html
    assert '<span class="v">v3</span>' in html and "Signature of v3" in html and "15<small>/16</small>" in html
    assert "2026-10-13 13:35 UTC, approved in the model registry" in html
    assert "13:36 UTC &middot; next check in 14 min" in html and "76 ms" in html
    assert 'id="clip"' in html and "MP4 up to 50 MB" in html
    assert "alarm" not in html.replace('class="lamp ok"', "")


def test_refused_release_shows_all_four_cues_and_keeps_the_running_model():
    fetch = {"version": "v4", "status": "rejected", "detail": "signature verification failed for release.json",
             "checked_at": "2026-10-13T13:51:00+00:00"}
    html, state = render(RELEASE_V3, fetch, SELFTEST_V3, minutes=15)
    assert state == "refused"
    assert 'class="lamp alarm" role="status">Release refused' in html          # 1 lamp
    assert 'class="alarm" role="alert"' in html and "<b>v4</b> was refused and not installed" in html  # 2 alarm
    assert "<strong>Signature check failed</strong>" in html and "<b>v3</b> is still running" in html
    assert "13:51 UTC, v4 refused &middot; next check in 15 min" in html       # 3 last check
    assert "<b>What to do:</b> ask the ML team to check release v4" in html    # 4 what to do
    assert 'class="panel alarmed"' in html and 'id="clip"' in html


def test_refusal_with_nothing_installed_says_no_model_runs():
    html, state = render(None, {"version": "v1", "status": "rejected", "detail": "sha256 mismatch",
                                "checked_at": "2026-10-13T13:51:00+00:00"})
    assert state == "refused" and "No model is installed" in html and "stays without a model" in html
    assert 'id="clip"' not in html


def test_no_release_yet_waits_and_disables_classify():
    html, state = render(fetch={"version": "", "status": "waiting", "checked_at": "2026-10-13T13:36:00+00:00"}, minutes=3)
    assert "13:36 UTC &middot; nothing approved yet" in html
    assert state == "no-release"
    assert 'class="lamp idle" role="status">No model yet' in html and "No release yet" in html
    assert "<dd>in 3 min</dd>" in html and "Classifying needs an installed model." in html
    assert 'id="clip"' not in html


def test_after_a_refusal_the_next_good_install_is_healthy_again():
    html, state = render(RELEASE_V3, {"version": "v3", "status": "verified", "checked_at": "2026-10-13T14:06:00+00:00"}, SELFTEST_V3)
    assert state == "healthy" and "refused" not in html


def test_state_text_is_escaped():
    html, _ = render(RELEASE_V3, {"version": "<script>x</script>", "status": "rejected", "detail": "",
                                  "checked_at": "2026-10-13T13:51:00+00:00"}, SELFTEST_V3)
    assert "<script>x" not in html and "&lt;script&gt;" in html


@pytest.mark.parametrize("detail, headline", [
    ("signature verification failed for /opt/conveyor/fetch/release.json", "Signature check failed"),
    ("sha256 mismatch: release.json says a, artefact is b", "Digest check failed"),
    ("channel names v2, older than the installed v3", "Older release refused"),
    ("release.json names version v5, expected v4", "Version mismatch"),
    ("channel names an invalid version", "Release refused"),
])
def test_the_headline_names_the_check_that_failed(detail, headline):
    html, _ = render(RELEASE_V3, {"version": "v4", "status": "rejected", "detail": detail,
                                  "checked_at": "2026-10-13T13:51:00+00:00"}, SELFTEST_V3)
    assert f"<strong>{headline}</strong>" in html


def test_a_self_test_of_an_earlier_release_is_not_shown_as_the_current_score():
    stale = {**SELFTEST_V3, "version": "v2"}
    html, _ = render(RELEASE_V3, {"version": "v3", "status": "verified", "checked_at": "2026-10-13T13:36:31+00:00"}, stale)
    assert "15<small>/16</small>" not in html and "measured after the self-test" in html
