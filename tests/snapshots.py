# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Builds a small dataset snapshot on disk: generated curated clips, held-out test
clips under <snapshot>/test, and the manifest the training job verifies them against."""

import json

from conftest import ROOT, import_from, write_clip

dataset = import_from(ROOT / "ml" / "train", "dataset")


def make_snapshot(tmp_path, groups=(("factory-a", "jam"), ("factory-b", "drop")), per_group=5, test_per_group=3):
    """Returns (train dir, snapshot dir holding manifest.json and test/)."""
    train, snapshot = tmp_path / "train", tmp_path / "snapshot"
    for g, (site, label) in enumerate(groups):
        for i in range(per_group):
            write_clip(train / site / label / f"{g}{i}.mp4", shade=40 * g + i)
        for i in range(test_per_group):
            write_clip(snapshot / "test" / site / label / f"{label}-{i:03d}.mp4", shade=40 * g + 20 + i)
    clips = [{"key": f"curated/{p.relative_to(train)}", "sha256": dataset.sha256_b64(p)} for p, _, _ in dataset.list_clips(train)]
    test = [{"path": str(p.relative_to(snapshot / "test")), "sha256": dataset.sha256_b64(p)}
            for p, _, _ in dataset.list_clips(snapshot / "test")]
    (snapshot / "manifest.json").write_text(json.dumps({"snapshot": "run-1", "prefix": "curated/", "clips": clips, "test_clips": test}))
    return train, snapshot
