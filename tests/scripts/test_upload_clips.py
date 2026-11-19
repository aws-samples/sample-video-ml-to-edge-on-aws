# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import io
import json

import pytest

from conftest import ROOT, import_from

upload_clips = import_from(ROOT / "scripts", "upload_clips")

# The shape lambdas/presign returns: every header is signed into the URL.
GRANT = {"url": "https://intake.example/intake/factory-a/jam/x.mp4?X-Amz-Signature=s", "key": "intake/factory-a/jam/x.mp4",
         "clipId": "x", "label": "jam", "expiresIn": 900,
         "headers": {"Content-Type": "video/mp4", "x-amz-tagging": "contributor=sub-1"}}


def test_the_put_carries_exactly_the_headers_presign_returned(monkeypatch, tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\x00" * 10)
    requests = []

    def urlopen(request, timeout):
        requests.append(request)
        return io.BytesIO(json.dumps(GRANT).encode() if request.full_url.endswith("/api/presign") else b"")

    monkeypatch.setattr(upload_clips.urllib.request, "urlopen", urlopen)
    assert upload_clips.upload_once("https://portal.example", "token", clip, "jam") == GRANT["key"]
    presign, put = requests
    assert json.loads(presign.data) == {"label": "jam", "size": 10}
    assert put.get_method() == "PUT" and put.full_url == GRANT["url"] and put.data == clip.read_bytes()
    # urllib stores header names capitalized; compare case-insensitively, as S3 does.
    assert {k.lower(): v for k, v in put.header_items()} == {k.lower(): v for k, v in GRANT["headers"].items()}


def test_a_presigned_url_that_is_not_https_is_refused(monkeypatch, tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\x00")
    grant = {**GRANT, "url": "http://intake.example/x.mp4"}
    monkeypatch.setattr(upload_clips.urllib.request, "urlopen", lambda request, timeout: io.BytesIO(json.dumps(grant).encode()))
    with pytest.raises(ValueError, match="not https"):
        upload_clips.upload_once("https://portal.example", "token", clip, "jam")
