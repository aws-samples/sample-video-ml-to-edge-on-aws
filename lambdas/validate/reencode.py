# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Writes a clean copy of a probed clip: only decoded pixels are re-encoded, so no
container metadata, extra streams, audio or attachments of the original survive."""

import cv2


def reencode(source: str, target: str, fps: float) -> int:
    """Re-encodes every frame of source into an MPEG-4 Part 2 MP4 at target and
    returns the number of frames written."""
    cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
    writer, frames = None, 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if writer is None:
                height, width = frame.shape[:2]
                writer = cv2.VideoWriter(target, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
                if not writer.isOpened():
                    raise RuntimeError("OpenCV could not open an mp4v writer")
            writer.write(frame)
            frames += 1
    finally:
        cap.release()
        if writer is not None:
            writer.release()
    return frames
