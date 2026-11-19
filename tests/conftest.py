# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]

# boto3 clients are created at import time; these keep them offline.
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


def import_from(directory: Path, module: str, env: dict | None = None):
    """Imports `module` from `directory` the way its runtime would, with env set,
    dropping any earlier import of a same-named module from another directory."""
    os.environ.update(env or {})
    for name in [module, "handler", "probe", "reencode", "classifier", "preprocess", "selftest", "ui"]:
        sys.modules.pop(name, None)
    sys.path.insert(0, str(directory))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.remove(str(directory))


def write_clip(path: Path, frames: int = 12, size=(64, 48), shade: int = 128, fourcc: str = "mp4v") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*fourcc), 12.0, size)
    assert writer.isOpened()
    rng = np.random.default_rng(shade)
    for t in range(frames):
        frame = np.full((size[1], size[0], 3), shade, dtype=np.uint8)
        frame[:, (t * 4) % size[0]] = 255 - shade
        frame += rng.integers(0, 8, frame.shape, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return path


@pytest.fixture
def clip(tmp_path) -> Path:
    return write_clip(tmp_path / "clip.mp4")
