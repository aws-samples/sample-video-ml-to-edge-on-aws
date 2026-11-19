# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from conftest import ROOT, import_from

ui = import_from(ROOT / "site" / "gateway", "ui")


class FakeClassifier:
    def __init__(self):
        self.bodies = []

    def predict(self, path):
        data = open(path, "rb").read()
        self.bodies.append(data)
        if data == b"broken":
            raise ValueError("no decodable frames in video")
        return {"label": "jam", "confidence": 0.93, "probabilities": {"jam": 0.93}, "latency_ms": 41.0}


@pytest.fixture
def server(tmp_path, monkeypatch):
    (tmp_path / "state").mkdir()
    (tmp_path / "model").mkdir()
    (tmp_path / "env").write_text("SITE=factory-a\nRELEASE_BUCKET=rel\nREGION=eu-west-1\n")  # pragma: allowlist secret
    (tmp_path / "model" / "release.json").write_text(json.dumps({"version": "v3", "released_at": "2026-10-13T13:35:00+00:00"}))
    (tmp_path / "state" / "fetch.json").write_text(json.dumps({"version": "v3", "status": "verified"}))
    (tmp_path / "state" / "selftest.json").write_text(json.dumps({"version": "v3", "accuracy": 0.875, "correct": 7, "total": 8, "mean_latency_ms": 41.0}))
    fake = FakeClassifier()
    monkeypatch.setattr(ui, "Classifier", lambda model_dir: fake)
    monkeypatch.setattr(ui, "first_frame", lambda path: "data:image/jpeg;base64,AAAA")
    # The fixtures send placeholder bytes; the probe is exercised on real files below.
    monkeypatch.setattr(ui, "probe", lambda path: (None, {}) if open(path, "rb").read() != b"image" else ("codec-not-allowed", {}))
    gateway = ui.Gateway(tmp_path, next_fetch=lambda: 7)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(gateway))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd, gateway, fake
    httpd.shutdown()


def request(httpd, method, path, body=None, host="127.0.0.1:8080", headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1])
    default = {"Content-Type": "video/mp4"} if method == "POST" else {}
    conn.request(method, path, body=body, headers={"Host": host, **default, **(headers or {})})
    response = conn.getresponse()
    return response.status, response.getheaders(), response.read()


def test_status_reports_fetch_and_selftest(server):
    status, headers, body = request(server[0], "GET", "/api/status")
    doc = json.loads(body)
    assert status == 200 and doc["fetch"]["status"] == "verified" and doc["selftest"]["accuracy"] == 0.875
    assert dict(headers)["Content-Security-Policy"].startswith("default-src 'self'")


def test_classify_returns_label_confidence_latency(server):
    httpd, _, fake = server
    status, _, body = request(httpd, "POST", "/api/classify", body=b"mp4-bytes", headers={"Content-Type": "video/mp4"})
    assert status == 200 and json.loads(body) == {"label": "jam", "confidence": 0.93, "probabilities": {"jam": 0.93},
                                                  "latency_ms": 41.0, "frame": "data:image/jpeg;base64,AAAA", "model": "v3"}
    assert fake.bodies == [b"mp4-bytes"]


def test_undecodable_clip_is_422_with_a_plain_reason(server):
    status, _, body = request(server[0], "POST", "/api/classify", body=b"broken")
    assert status == 422 and json.loads(body)["error"] == "not a supported video"


def test_empty_or_oversized_upload_is_413(server, monkeypatch):
    monkeypatch.setattr(ui, "MAX_UPLOAD", 4)
    assert request(server[0], "POST", "/api/classify", body=b"")[0] == 413
    assert request(server[0], "POST", "/api/classify", body=b"12345")[0] == 413


@pytest.mark.parametrize("host", ["evil.example:8080", "127.0.0.1:9999", ""])
def test_foreign_host_header_is_refused(server, host):
    assert request(server[0], "GET", "/api/status", host=host)[0] == 421
    assert request(server[0], "POST", "/api/classify", body=b"x", host=host)[0] == 421


def test_no_release_installed_is_503(server):
    httpd, gateway, _ = server
    gateway.classifier = None
    assert request(httpd, "POST", "/api/classify", body=b"x")[0] == 503


def test_page_and_unknown_path(server):
    status, headers, body = request(server[0], "GET", "/")
    assert status == 200 and b"GATEWAY <span>&middot;</span> factory-a" in body and b"next check in 7 min" in body
    assert "img-src 'self' data:" in dict(headers)["Content-Security-Policy"]
    assert request(server[0], "GET", "/gateway.css")[0] == 200
    assert request(server[0], "GET", "/../ui.py")[0] == 404


def test_gateway_without_model_has_no_classifier(tmp_path):
    (tmp_path / "env").write_text("SITE=factory-b\n")
    gateway = ui.Gateway(tmp_path, next_fetch=lambda: None)
    assert gateway.classifier is None and gateway.site == "factory-b"
    assert gateway.status() == {"release": None, "fetch": None, "selftest": None}


def test_next_fetch_reads_the_systemd_timer(monkeypatch):
    now = ui.datetime(2026, 10, 13, 16, 45, 47, tzinfo=ui.timezone.utc)

    class Done:
        # systemd 252 `list-timers --output=json`, captured on a gateway.
        stdout = json.dumps([{"next": int((now.timestamp() + 16.5 * 60) * 1e6), "unit": "conveyor-fetch.timer"}])

    monkeypatch.setattr(ui.subprocess, "run", lambda *a, **k: Done())
    monkeypatch.setattr(ui, "datetime", type("Clock", (ui.datetime,), {"now": staticmethod(lambda tz=None: now)}))
    assert ui.minutes_to_next_fetch() == 16


def test_next_fetch_is_unknown_without_the_timer(monkeypatch):
    class Done:
        stdout = "[]"

    monkeypatch.setattr(ui.subprocess, "run", lambda *a, **k: Done())
    assert ui.minutes_to_next_fetch() is None


def test_a_still_image_renamed_mp4_is_refused_before_the_model_sees_it(server):
    httpd, _, fake = server
    status, _, body = request(httpd, "POST", "/api/classify", body=b"image")
    assert status == 422 and json.loads(body)["error"] == "not a supported video" and fake.bodies == []


def test_the_real_probe_refuses_a_png(tmp_path):
    import cv2
    import numpy as np
    png = tmp_path / "snapshot.mp4"
    png.write_bytes(cv2.imencode(".png", np.zeros((32, 32, 3), np.uint8))[1].tobytes())
    assert ui.probe(str(png))[0] == "codec-not-allowed"


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data"])
def test_non_mp4_post_never_reaches_the_decoder(server, content_type):
    httpd, _, fake = server
    assert request(httpd, "POST", "/api/classify", body=b"x", headers={"Content-Type": content_type})[0] == 415
    assert fake.bodies == []
