# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import json
import sys

import cv2
import numpy as np
import pytest

from conftest import ROOT, import_from, write_clip
from fakes import FakeS3

ENV = {"INTAKE_BUCKET": "intake", "CURATED_BUCKET": "curated", "SITES": "factory-a,factory-b",
       "LABELS": "normal,jam,drop,empty"}
CLIP = "0123456789abcdef0123456789abcdef"  # pragma: allowlist secret


@pytest.fixture
def validate():
    return import_from(ROOT / "lambdas" / "validate", "handler", ENV)


def scan_event(key, status="NO_THREATS_FOUND", bucket="intake"):
    return {"detail": {"s3ObjectDetails": {"bucketName": bucket, "objectKey": key, "versionId": "v1"},
                       "scanResultDetails": {"scanResultStatus": status}}}


def run(validate, monkeypatch, data, key=f"intake/factory-a/jam/{CLIP}.mp4", **event):
    fake = FakeS3({("intake", key): data})
    monkeypatch.setattr(validate, "s3", fake)
    return validate.main(scan_event(key, **event), None), fake


def test_clean_clip_is_reencoded_into_curated(validate, monkeypatch, clip):
    result, fake = run(validate, monkeypatch, clip.read_bytes())
    put = fake.puts[("curated", f"curated/factory-a/jam/{CLIP}.mp4")]
    assert result["frames"] == 12
    assert put["ChecksumAlgorithm"] == "SHA256"
    assert put["Body"] != clip.read_bytes()
    assert fake.downloads == [("intake", f"intake/factory-a/jam/{CLIP}.mp4", {"VersionId": "v1"})]


def test_reencoded_copy_drops_metadata(validate, monkeypatch, tmp_path, clip):
    # Bytes appended after the media data survive a byte copy but not a re-encode.
    marked = clip.read_bytes() + b"GPS-48.8566N-2.3522E-OWNER-JANE"
    _, fake = run(validate, monkeypatch, marked)
    assert b"OWNER-JANE" not in fake.puts[("curated", f"curated/factory-a/jam/{CLIP}.mp4")]["Body"]


def test_image_renamed_to_mp4_is_rejected(validate, monkeypatch, tmp_path):
    ok, png = cv2.imencode(".png", np.zeros((32, 32, 3), np.uint8))
    result, fake = run(validate, monkeypatch, png.tobytes())
    assert result["reason"] == "codec-not-allowed"
    record = json.loads(fake.puts[("curated", f"rejected/factory-a/jam/{CLIP}.json")]["Body"])
    assert record["reason"] == "codec-not-allowed"
    assert not [k for k in fake.puts if k[1].startswith("curated/")]


def test_garbage_is_rejected(validate, monkeypatch):
    result, _ = run(validate, monkeypatch, b"\x00" * 4096)
    assert result["reason"] in {"not-decodable", "no-video-stream"}


def test_tail_truncated_clip_is_not_decodable(validate, monkeypatch, tmp_path):
    # OpenCV writes the MP4 index last, so a cut-off upload loses it.
    data = write_clip(tmp_path / "long.mp4", frames=60, size=(160, 120)).read_bytes()
    result, _ = run(validate, monkeypatch, data[: len(data) * 2 // 3])
    assert result["reason"] == "not-decodable"


def test_clip_whose_frames_stop_early_is_truncated(validate, monkeypatch):
    probe_module = sys.modules["probe"]

    class ShortCapture:
        """Declares 30 frames but decodes 10, like a clip with a damaged tail."""
        props = {cv2.CAP_PROP_FOURCC: cv2.VideoWriter_fourcc(*"FMP4"), cv2.CAP_PROP_FRAME_WIDTH: 64,
                 cv2.CAP_PROP_FRAME_HEIGHT: 48, cv2.CAP_PROP_FPS: 12, cv2.CAP_PROP_FRAME_COUNT: 30}

        def __init__(self, *args):
            self.left = 10

        def isOpened(self):
            return True

        def get(self, prop):
            return self.props[prop]

        def read(self):
            self.left -= 1
            return (True, np.zeros((48, 64, 3), np.uint8)) if self.left >= 0 else (False, None)

        def release(self):
            pass

    monkeypatch.setattr(probe_module.cv2, "VideoCapture", ShortCapture)
    assert probe_module.probe("ignored.mp4") == ("truncated", {"fourcc": "FMP4", "width": 64, "height": 48, "fps": 12,
                                                              "frame_count": 30, "decoded": 10})


@pytest.mark.parametrize("key", [f"intake/factory-z/jam/{CLIP}.mp4", f"intake/factory-a/fire/{CLIP}.mp4",
                                 "intake/factory-a/jam/../../x.mp4", f"curated/factory-a/jam/{CLIP}.mp4"])
def test_unexpected_keys_are_ignored(validate, monkeypatch, clip, key):
    result, fake = run(validate, monkeypatch, clip.read_bytes(), key=key)
    assert result["reason"] == "unexpected-key" and not fake.puts and not fake.downloads


def test_other_scan_results_and_buckets_are_skipped(validate, monkeypatch, clip):
    for kwargs in ({"status": "THREATS_FOUND"}, {"bucket": "elsewhere"}):
        result, fake = run(validate, monkeypatch, clip.read_bytes(), **kwargs)
        assert "skipped" in result and not fake.downloads


def test_oversized_clip_is_rejected(validate, monkeypatch, tmp_path):
    data = write_clip(tmp_path / "big.mp4", frames=2, size=(1936, 64)).read_bytes()
    result, fake = run(validate, monkeypatch, data)
    assert result["reason"] == "too-large" and not [k for k in fake.puts if k[1].startswith("curated/")]


def test_reencode_that_loses_a_frame_is_rejected(validate, monkeypatch, clip):
    real = validate.reencode
    monkeypatch.setattr(validate, "reencode", lambda src, dst, fps: real(src, dst, fps) - 1)
    result, fake = run(validate, monkeypatch, clip.read_bytes())
    assert result["reason"] == "reencode-frame-mismatch" and not [k for k in fake.puts if k[1].startswith("curated/")]
