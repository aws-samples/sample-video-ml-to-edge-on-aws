# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Local operator UI of the site gateway, standard library only.

    python ui.py [/opt/conveyor]

Listens on 127.0.0.1:8080 only; operators reach it through an SSM port-forwarding
session. GET / renders the page from the state files (page.py); GET /api/status
returns those files. POST /api/classify takes an MP4 of at most 50 MB as the raw
request body and answers the label, the score of every label, the latency, the
installed version and the clip's first frame.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import page
from classifier import Classifier
from frame import first_frame
from probe import probe

HOST, PORT = "127.0.0.1", 8080
MAX_UPLOAD = 50 * 1024 * 1024
STATIC = Path(__file__).resolve().parent / "static"
FILES = {"/app.js": ("app.js", "text/javascript"), "/gateway.css": ("gateway.css", "text/css"),
         "/tokens.css": ("tokens.css", "text/css")}
# Only names a port-forwarded browser sends; another Host means a page elsewhere
# is trying to reach the UI through DNS rebinding.
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
# The plain words the portal also uses for the validation probe's reasons.
REASONS = {
    "codec-not-allowed": "not a supported video",
    "no-video-stream": "no video stream in the file",
    "not-decodable": "the video could not be decoded",
    "truncated": "the video is cut short",
    "too-large": "frames larger than 1920 pixels",
    "too-many-frames": "longer than 10,000 frames",
}
HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}


def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def minutes_to_next_fetch() -> int | None:
    """Minutes until the systemd timer next runs the fetch, or None if unknown.
    The timer is monotonic (OnUnitActiveSec), so `list-timers` gives the next run
    as wall-clock microseconds while `show` has no realtime value for it."""
    out = subprocess.run(["systemctl", "list-timers", "conveyor-fetch.timer", "--all", "--output=json"],
                         capture_output=True, text=True).stdout
    try:
        next_us = json.loads(out)[0]["next"]
    except (ValueError, IndexError, KeyError, TypeError):
        return None
    return max(0, int((next_us / 1e6 - datetime.now(timezone.utc).timestamp()) // 60))


def site_of(base: Path) -> str:
    for line in (base / "env").read_text().splitlines():
        if line.startswith("SITE="):
            return line.split("=", 1)[1]
    raise ValueError("no SITE in env")


class Gateway:
    """The installed release, loaded once: fetch_release.sh restarts the UI after
    installing a new one."""

    def __init__(self, base: Path, next_fetch=minutes_to_next_fetch):
        self.base = base
        self.site = site_of(base)
        self.next_fetch = next_fetch
        self.classifier = Classifier(base / "model") if (base / "model").exists() else None

    def status(self) -> dict:
        return {
            "release": read_json(self.base / "model" / "release.json"),
            "fetch": read_json(self.base / "state" / "fetch.json"),
            "selftest": read_json(self.base / "state" / "selftest.json"),
        }


def make_handler(gateway: Gateway):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for name, value in HEADERS.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, status: int, doc: dict) -> None:
            self.send(status, json.dumps(doc).encode(), "application/json")

        def host_allowed(self) -> bool:
            if self.headers.get("Host") in ALLOWED_HOSTS:
                return True
            self.send_json(421, {"error": "unexpected Host header"})
            return False

        def do_GET(self):
            if not self.host_allowed():
                return
            if self.path == "/api/status":
                return self.send_json(200, gateway.status())
            if self.path == "/":
                html = page.render(gateway.status(), gateway.site, gateway.next_fetch(), MAX_UPLOAD // 2**20)
                return self.send(200, html.encode(), "text/html; charset=utf-8")
            if self.path in FILES:
                name, content_type = FILES[self.path]
                return self.send(200, (STATIC / name).read_bytes(), content_type)
            self.send_json(404, {"error": "not found"})

        def do_POST(self):
            if not self.host_allowed():
                return
            if self.path != "/api/classify":
                return self.send_json(404, {"error": "not found"})
            # A cross-site page can POST text/plain without a preflight; only an
            # explicit video/mp4 body reaches the decoder.
            if self.headers.get("Content-Type") != "video/mp4":
                return self.send_json(415, {"error": "Content-Type must be video/mp4"})
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= MAX_UPLOAD:
                return self.send_json(413, {"error": f"larger than the {MAX_UPLOAD // 2**20} MB limit of this gateway"})
            classifier = gateway.classifier
            if classifier is None:
                return self.send_json(503, {"error": "no release installed"})
            with tempfile.NamedTemporaryFile(suffix=".mp4") as clip:
                clip.write(self.rfile.read(length))
                clip.flush()
                reason, _ = probe(clip.name)
                if reason:
                    return self.send_json(422, {"error": REASONS.get(reason, "not a supported video")})
                try:
                    result = classifier.predict(clip.name)
                    result["frame"] = first_frame(clip.name)
                except ValueError:
                    return self.send_json(422, {"error": "not a supported video"})
            result["model"] = gateway.status()["release"]["version"]
            self.send_json(200, result)

        def log_message(self, fmt, *args):
            sys.stderr.write("ui %s\n" % (fmt % args))

    return Handler


def main() -> None:
    base = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/conveyor")
    server = ThreadingHTTPServer((HOST, PORT), make_handler(Gateway(base)))
    print(f"listening on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
