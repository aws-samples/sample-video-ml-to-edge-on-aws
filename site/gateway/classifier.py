# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Loads an installed release once and classifies clips on the CPU.

The release ships the preprocess.py it was trained with, so the gateway decodes
clips with exactly that code and CLIP_FORMAT, both covered by the release signature.
"""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort


def load_preprocess(model_dir: Path):
    spec = importlib.util.spec_from_file_location("release_preprocess", model_dir / "preprocess.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Classifier:
    def __init__(self, model_dir: Path):
        model_dir = Path(model_dir)
        self.labels: list[str] = json.loads((model_dir / "labels.json").read_text())
        self.preprocess = load_preprocess(model_dir)
        self.session = ort.InferenceSession(str(model_dir / "model.onnx"), providers=["CPUExecutionProvider"])

    def predict(self, clip_path: str) -> dict:
        """{label, confidence, probabilities, latency_ms}; raises ValueError when the
        clip does not decode. Latency covers decoding and inference."""
        start = time.perf_counter()
        clip = self.preprocess.load_clip(clip_path, **self.preprocess.CLIP_FORMAT)
        logits = self.session.run(["logits"], {"clip": clip[None]})[0][0].astype(np.float64)
        exp = np.exp(logits - logits.max())
        probs = exp / exp.sum()
        best = int(probs.argmax())
        return {
            "label": self.labels[best],
            "confidence": round(float(probs[best]), 4),
            "probabilities": {label: round(float(p), 4) for label, p in zip(self.labels, probs)},
            "latency_ms": round((time.perf_counter() - start) * 1000, 1),
        }
