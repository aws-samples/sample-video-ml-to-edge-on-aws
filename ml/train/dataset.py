# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""The training job's view of a dataset snapshot: which clips it holds, proof that
they are the clips the snapshot froze, the train/validation split and the self-test
clips."""

import base64
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path


def list_clips(train_dir: Path) -> list[tuple[Path, str, str]]:
    """(path, site, label) for every <site>/<label>/<clip>.mp4 under train_dir."""
    clips = [(p, p.parent.parent.name, p.parent.name) for p in sorted(train_dir.glob("*/*/*.mp4"))]
    if not clips:
        raise SystemExit(f"no <site>/<label>/*.mp4 clips under {train_dir}")
    return clips


def sha256_b64(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return base64.b64encode(digest.digest()).decode()


def verify_files(directory: Path, expected: dict[str, str], what: str) -> None:
    """Exits unless the clips under directory are exactly `expected` (relative path
    to base64 SHA-256)."""
    present = {str(p.relative_to(directory)): p for p, _, _ in list_clips(directory)}
    if set(present) != set(expected):
        missing, extra = sorted(set(expected) - set(present)), sorted(set(present) - set(expected))
        raise SystemExit(f"{what} mismatch: missing={missing[:5]} extra={extra[:5]}")
    changed = [rel for rel, path in present.items() if sha256_b64(path) != expected[rel]]
    if changed:
        raise SystemExit(f"{what} mismatch: {len(changed)} clip(s) changed since the snapshot, e.g. {changed[:3]}")


def verify_snapshot(train_dir: Path, snapshot_dir: Path) -> dict:
    """Exits unless the files under train_dir are exactly the snapshot's curated clips
    with the SHA-256 checksums S3 recorded for the snapshotted object versions, and
    the files under snapshot_dir/test are exactly its held-out test clips."""
    manifest = json.loads((snapshot_dir / "manifest.json").read_text())
    prefix = manifest["prefix"]
    verify_files(train_dir, {c["key"][len(prefix):]: c["sha256"] for c in manifest["clips"]}, "snapshot")
    verify_files(snapshot_dir / "test", {c["path"]: c["sha256"] for c in manifest["test_clips"]}, "test set")
    return manifest


def split(clips, val_fraction: float, seed: int):
    """Per (site, label) split, so every site and label is in both sets; a group of
    one clip goes to training."""
    groups = defaultdict(list)
    for clip in clips:
        groups[(clip[1], clip[2])].append(clip)
    rng = random.Random(seed)
    train, val = [], []
    for key in sorted(groups):
        members = groups[key][:]
        rng.shuffle(members)
        n_val = min(len(members) - 1, round(len(members) * val_fraction))
        val += members[:n_val]
        train += members[n_val:]
    return train, val


def selftest_clips(test, per_group: int):
    """The first `per_group` test clips of each (site, label): held out from training
    and model selection, and shipped in the release for the gateway's self-test."""
    picked, counts = [], defaultdict(int)
    for clip in test:
        if counts[(clip[1], clip[2])] < per_group:
            counts[(clip[1], clip[2])] += 1
            picked.append(clip)
    return picked
