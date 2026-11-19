# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import base64
import hashlib
import json

import pytest

from conftest import ROOT, import_from

snapshot = import_from(ROOT / "scripts", "snapshot")


class FakeS3:
    def __init__(self, keys):
        self.keys = keys
        self.puts = {}

    def get_paginator(self, _name):
        keys = self.keys

        class Paginator:
            def paginate(self, Bucket, Prefix):
                yield {"Contents": [{"Key": k} for k in keys if k.startswith(Prefix)]}
        return Paginator()

    def head_object(self, Bucket, Key, ChecksumMode):
        assert ChecksumMode == "ENABLED"
        return {"VersionId": f"ver-{Key[-6:-4]}", "ChecksumSHA256": f"sum-{Key[-6:-4]}", "ContentLength": 10}

    def put_object(self, Bucket, Key, Body, ChecksumSHA256=None):
        if ChecksumSHA256 is not None:
            # What S3 does with a declared checksum.
            assert base64.b64encode(hashlib.sha256(Body).digest()).decode() == ChecksumSHA256, f"BadDigest {Key}"
            self.puts[(Bucket, Key)] = Body
        else:
            self.puts[(Bucket, Key)] = json.loads(Body)


@pytest.fixture
def dataset_dir(tmp_path):
    """A local dataset in the fetch_dataset layout with one test clip per site."""
    files = []
    for site, split, label, data in [("factory-a", "test", "jam", b"a-jam"), ("factory-b", "test", "jam", b"b-jam"),
                                     ("factory-a", "train", "jam", b"train")]:
        path = f"{site}/{split}/{label}/{label}-000.mp4"
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_bytes(data)
        files.append({"path": path, "site": site, "split": split, "label": label, "sha256": hashlib.sha256(data).hexdigest()})
    (tmp_path / "manifest.json").write_text(json.dumps({"files": files}))
    return tmp_path


def test_snapshot_freezes_versions_and_names_the_same_clips(dataset_dir):
    s3 = FakeS3(["curated/factory-a/jam/aa.mp4", "curated/factory-b/drop/bb.mp4", "curated/notes.txt"])
    result = snapshot.build(s3, "cur", "ml", "run-1", dataset_dir)
    manifest = s3.puts[("ml", "manifests/run-1/manifest.json")]
    sm = s3.puts[("ml", "manifests/run-1/train.manifest")]
    assert [c["version_id"] for c in manifest["clips"]] == ["ver-aa", "ver-bb"]
    assert sm == [{"prefix": "s3://cur/curated/"}, "factory-a/jam/aa.mp4", "factory-b/drop/bb.mp4"]
    assert result["num_clips"] == 2 and result["snapshot_uri"] == "s3://ml/manifests/run-1/"


def test_snapshot_carries_only_the_test_split_with_its_digests(dataset_dir):
    s3 = FakeS3(["curated/factory-a/jam/aa.mp4"])
    result = snapshot.build(s3, "cur", "ml", "run-1", dataset_dir)
    assert s3.puts[("ml", "manifests/run-1/test/factory-a/jam/jam-000.mp4")] == b"a-jam"
    assert s3.puts[("ml", "manifests/run-1/test/factory-b/jam/jam-000.mp4")] == b"b-jam"
    assert sorted(k for _, k in s3.puts if k.endswith(".mp4")) == [
        "manifests/run-1/test/factory-a/jam/jam-000.mp4", "manifests/run-1/test/factory-b/jam/jam-000.mp4"]
    tests = s3.puts[("ml", "manifests/run-1/manifest.json")]["test_clips"]
    assert tests == [{"path": "factory-a/jam/jam-000.mp4", "sha256": base64.b64encode(hashlib.sha256(b"a-jam").digest()).decode()},
                     {"path": "factory-b/jam/jam-000.mp4", "sha256": base64.b64encode(hashlib.sha256(b"b-jam").digest()).decode()}]
    assert result["num_test_clips"] == 2


def test_test_clip_changed_since_the_dataset_was_fetched_is_refused(dataset_dir):
    (dataset_dir / "factory-b/test/jam/jam-000.mp4").write_bytes(b"edited")
    with pytest.raises(AssertionError, match="BadDigest"):
        snapshot.build(FakeS3(["curated/factory-a/jam/aa.mp4"]), "cur", "ml", "run-1", dataset_dir)


def test_missing_dataset_says_how_to_fetch_it(tmp_path):
    with pytest.raises(SystemExit, match="fetch_dataset.py"):
        snapshot.build(FakeS3(["curated/factory-a/jam/aa.mp4"]), "cur", "ml", "run-1", tmp_path)


def test_empty_curated_set_refuses(dataset_dir):
    with pytest.raises(SystemExit):
        snapshot.build(FakeS3([]), "cur", "ml", "run-1", dataset_dir)


def test_duplicate_checksum_is_frozen_once(dataset_dir):
    s3 = FakeS3(["curated/factory-a/jam/aa.mp4", "curated/factory-a/jam/xaa.mp4"])
    # Both keys end in "aa", so the fake reports the same checksum for both.
    snapshot.build(s3, "cur", "ml", "run-1", dataset_dir)
    assert [c["key"] for c in s3.puts[("ml", "manifests/run-1/manifest.json")]["clips"]] == ["curated/factory-a/jam/aa.mp4"]
