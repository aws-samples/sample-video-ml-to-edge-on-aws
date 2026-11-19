# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import pytest

from conftest import ROOT, import_from, write_clip
from snapshots import make_snapshot

dataset = import_from(ROOT / "ml" / "train", "dataset")


def test_snapshot_verifies(tmp_path):
    train, snapshot = make_snapshot(tmp_path)
    assert dataset.verify_snapshot(train, snapshot)["snapshot"] == "run-1"


def test_changed_clip_fails_snapshot(tmp_path):
    train, snapshot = make_snapshot(tmp_path)
    write_clip(train / "factory-a" / "jam" / "00.mp4", shade=200)
    with pytest.raises(SystemExit, match="changed since the snapshot"):
        dataset.verify_snapshot(train, snapshot)


def test_extra_clip_fails_snapshot(tmp_path):
    train, snapshot = make_snapshot(tmp_path)
    write_clip(train / "factory-a" / "jam" / "late.mp4")
    with pytest.raises(SystemExit, match="extra"):
        dataset.verify_snapshot(train, snapshot)


def test_changed_test_clip_fails_snapshot(tmp_path):
    train, snapshot = make_snapshot(tmp_path)
    write_clip(snapshot / "test" / "factory-b" / "drop" / "drop-000.mp4", shade=200)
    with pytest.raises(SystemExit, match="test set mismatch: 1 clip"):
        dataset.verify_snapshot(train, snapshot)


def test_missing_test_clip_fails_snapshot(tmp_path):
    train, snapshot = make_snapshot(tmp_path)
    (snapshot / "test" / "factory-a" / "jam" / "jam-001.mp4").unlink()
    with pytest.raises(SystemExit, match="test set mismatch: missing=.*jam-001"):
        dataset.verify_snapshot(train, snapshot)


def test_split_is_per_site_and_label_and_deterministic(tmp_path):
    train, _ = make_snapshot(tmp_path)
    clips = dataset.list_clips(train)
    tr, va = dataset.split(clips, 0.2, seed=0)
    assert {(s, l) for _, s, l in va} == {("factory-a", "jam"), ("factory-b", "drop")}
    assert len(va) == 2 and len(tr) == 8 and not {c[0] for c in tr} & {c[0] for c in va}
    assert dataset.split(clips, 0.2, seed=0) == (tr, va)


def test_single_clip_group_goes_to_training(tmp_path):
    train, _ = make_snapshot(tmp_path, groups=(("factory-a", "jam"),), per_group=1)
    tr, va = dataset.split(dataset.list_clips(train), 0.5, seed=0)
    assert len(tr) == 1 and va == []


def test_selftest_takes_two_test_clips_per_site_and_label(tmp_path):
    _, snapshot = make_snapshot(tmp_path, test_per_group=5)
    test = dataset.list_clips(snapshot / "test")
    picked = dataset.selftest_clips(test, 2)
    assert len(picked) == 4 and set(picked) <= set(test)
    assert sorted((s, l) for _, s, l in picked) == [("factory-a", "jam")] * 2 + [("factory-b", "drop")] * 2
