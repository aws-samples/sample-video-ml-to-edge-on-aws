# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""The first frame of an uploaded clip as a JPEG data URI, so the operator sees
what the camera saw next to the label."""

from __future__ import annotations

import base64

import cv2

WIDTH = 640


def first_frame(path: str) -> str:
    """Raises ValueError when the clip has no decodable frame."""
    cap = cv2.VideoCapture(path)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise ValueError("no decodable frames in video")
    h, w = frame.shape[:2]
    frame = cv2.resize(frame, (WIDTH, round(h * WIDTH / w)), interpolation=cv2.INTER_AREA)
    ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(jpeg.tobytes()).decode()
