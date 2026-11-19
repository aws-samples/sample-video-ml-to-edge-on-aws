# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""OpenCV-only video probe.

probe(path) returns (reason, info): reason is None when the file holds a video
stream in an allowed codec whose every frame decodes, otherwise why it is rejected.
The validation function and the gateway UI run this same file; the site bundle
copies it in at build time.
"""

from __future__ import annotations

import cv2

# Fourccs as the reader reports them: H.264, H.265, MPEG-4 Part 2 (OpenCV's mp4v
# writer produces FMP4), VP9.
ALLOWED = {"h264", "avc1", "hevc", "hvc1", "FMP4", "mp4v", "VP90"}
MAX_FRAMES = 10_000
MAX_SIDE = 1920


def fourcc_str(code: float) -> str:
    code = int(code)
    return "".join(chr((code >> 8 * i) & 0xFF) for i in range(4)).strip("\x00")


def probe(path: str) -> tuple[str | None, dict]:
    cap = cv2.VideoCapture(path, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        return "not-decodable", {}
    info = {
        "fourcc": fourcc_str(cap.get(cv2.CAP_PROP_FOURCC)),
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fps": round(cap.get(cv2.CAP_PROP_FPS), 3),
        "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
    }
    if info["width"] <= 0 or info["height"] <= 0:
        cap.release()
        return "no-video-stream", info
    # A PNG renamed to .mp4 opens as a one-frame video; only the allowlist stops it.
    if info["fourcc"] not in ALLOWED:
        cap.release()
        return "codec-not-allowed", info
    if max(info["width"], info["height"]) > MAX_SIDE:
        cap.release()
        return "too-large", info
    decoded = 0
    while decoded <= MAX_FRAMES:
        ok, frame = cap.read()
        if not ok or frame.shape[:2] != (info["height"], info["width"]):
            break
        decoded += 1
    cap.release()
    info["decoded"] = decoded
    if decoded > MAX_FRAMES:
        return "too-many-frames", info
    if decoded < 1:
        return "not-decodable", info
    if decoded < info["frame_count"]:
        return "truncated", info
    return None, info
