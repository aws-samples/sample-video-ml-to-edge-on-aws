# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Clip decoding shared by training and the site gateway.

Training copies this file into its source bundle and writes CLIP_FORMAT into the
release as preprocess.json; the gateway decodes with the values from that file,
so a model is always fed clips shaped the way it was trained. A clip becomes a
float32 array of shape (3, FRAMES, SIZE, SIZE) in channels, time, height, width
order; the caller adds the batch dimension.
"""

import cv2
import numpy as np

CLIP_FORMAT = {
    "frames": 16,
    "size": 112,
    "resize_short": 128,
    "mean": [0.43216, 0.394666, 0.37645],
    "std": [0.22803, 0.22145, 0.216989],
}


def read_frames(path: str) -> list:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"cannot open video: {path}")
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    if not frames:
        raise ValueError(f"no decodable frames in video: {path}")
    return frames


def _resize_short_then_center_crop(frame: np.ndarray, resize_short: int, size: int) -> np.ndarray:
    h, w = frame.shape[:2]
    scale = resize_short / min(h, w)
    new_w, new_h = max(size, round(w * scale)), max(size, round(h * scale))
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
    top, left = (new_h - size) // 2, (new_w - size) // 2
    return resized[top:top + size, left:left + size]


def load_clip(path: str, frames: int, size: int, resize_short: int, mean, std) -> np.ndarray:
    """Samples `frames` frames uniformly across the video (a shorter video repeats
    frames), converts BGR to RGB, resizes the short side to resize_short,
    centre-crops size x size, scales to [0, 1] and normalises with mean and std."""
    decoded = read_frames(path)
    indices = np.linspace(0, len(decoded) - 1, num=frames).round().astype(int)
    mean_arr = np.asarray(mean, dtype=np.float32).reshape(1, 1, 3)
    std_arr = np.asarray(std, dtype=np.float32).reshape(1, 1, 3)
    stack = np.empty((frames, size, size, 3), dtype=np.float32)
    for t, idx in enumerate(indices):
        rgb = cv2.cvtColor(decoded[idx], cv2.COLOR_BGR2RGB)
        crop = _resize_short_then_center_crop(rgb, resize_short, size)
        stack[t] = (crop.astype(np.float32) / 255.0 - mean_arr) / std_arr
    return np.ascontiguousarray(stack.transpose(3, 0, 1, 2))
