# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Trains tiny3d for two epochs on generated clips with the real training entry
point, then installs the output as the gateway would and runs its self-test and
classifier on it. Needs torch."""

import json
import os
import subprocess
import sys

from conftest import ROOT, import_from
from snapshots import make_snapshot


def test_training_output_runs_on_the_gateway(tmp_path):
    train, snapshot = make_snapshot(tmp_path, per_group=6)
    model_dir = tmp_path / "model"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "shared")}
    run = subprocess.run([sys.executable, str(ROOT / "ml" / "train" / "train.py"), "--epochs", "2", "--batch-size", "4",
                          "--train-dir", str(train), "--snapshot-dir", str(snapshot), "--model-dir", str(model_dir)],
                         env=env, capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, run.stderr[-3000:]
    assert "epoch=2 train_loss=" in run.stdout and "test_accuracy=" in run.stdout

    metrics = json.loads((model_dir / "metrics.json").read_text())
    assert metrics["arch"] == "tiny3d" and metrics["num_val"] == 2 and metrics["snapshot"] == "run-1"
    assert metrics["num_test"] == 6 and 0 <= metrics["test_accuracy"] <= 1 and 1 <= metrics["selected_epoch"] <= 2
    assert set(metrics["test_accuracy_per_label"]) == {"drop", "jam"} and "val_accuracy" not in metrics
    assert metrics["onnx_max_abs_diff"] < 1e-3
    assert json.loads((model_dir / "labels.json").read_text()) == ["drop", "jam"]
    assert (model_dir / "preprocess.py").read_bytes() == (ROOT / "shared" / "preprocess.py").read_bytes()
    # Two test clips per site and label, never a training or validation clip.
    shipped = sorted(p.relative_to(model_dir / "selftest").as_posix() for p in (model_dir / "selftest").glob("*/*.mp4"))
    assert shipped == ["drop/factory-b-drop-000.mp4", "drop/factory-b-drop-001.mp4",
                       "jam/factory-a-jam-000.mp4", "jam/factory-a-jam-001.mp4"]

    # fetch_release.sh installs the verified release.json beside the model.
    (model_dir / "release.json").write_text(json.dumps({"version": "v1"}))
    selftest = import_from(ROOT / "site" / "gateway", "selftest")
    result = selftest.run(model_dir)
    assert result["total"] == 4 and result["version"] == "v1" and 0 <= result["accuracy"] <= 1
    prediction = selftest.Classifier(model_dir).predict(str(next((model_dir / "selftest").glob("*/*.mp4"))))
    assert prediction["label"] in ("drop", "jam") and prediction["latency_ms"] > 0
