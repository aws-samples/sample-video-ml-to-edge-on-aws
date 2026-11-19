# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Freezes the clips for one training run (scripts/train_job.py calls build before
each job). Writes under manifests/<run>/ in the ML bucket:
  manifest.json   every curated clip with its version id and S3 SHA-256 checksum,
                  and every held-out test clip with its SHA-256, which the training
                  job verifies each downloaded clip against
  train.manifest  the SageMaker ManifestFile that names exactly those curated clips
  test/<site>/<label>/<clip>.mp4
                  the test split of the local dataset, which contributors never
                  upload: the job scores the model on it and draws the self-test
                  clips from it
"""

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PREFIX = "curated/"


def curated_clips(s3, bucket: str) -> list[dict]:
    """Every curated clip once: a clip contributed twice re-encodes to the same
    bytes, so a repeated checksum is a duplicate and would leak across the split."""
    clips, seen = [], set()
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=PREFIX):
        for obj in page.get("Contents", []):
            if not obj["Key"].endswith(".mp4"):
                continue
            head = s3.head_object(Bucket=bucket, Key=obj["Key"], ChecksumMode="ENABLED")
            if head["ChecksumSHA256"] in seen:
                continue
            seen.add(head["ChecksumSHA256"])
            clips.append({"key": obj["Key"], "version_id": head["VersionId"],
                          "sha256": head["ChecksumSHA256"], "size": head["ContentLength"]})
    return clips


def held_out_clips(dataset_dir: Path) -> list[dict]:
    """The dataset's test split as <site>/<label>/<clip>.mp4 paths with the base64
    SHA-256 that S3 and the training job check, from the dataset manifest."""
    manifest_path = dataset_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"no {manifest_path}: fetch the dataset first (scripts/fetch_dataset.py)")
    files = [f for f in json.loads(manifest_path.read_text())["files"] if f["split"] == "test"]
    if not files:
        raise SystemExit(f"{manifest_path} lists no test clips")
    return [{"path": f"{f['site']}/{f['label']}/{Path(f['path']).name}", "source": dataset_dir / f["path"],
             "sha256": base64.b64encode(bytes.fromhex(f["sha256"])).decode()} for f in files]


def build(s3, curated_bucket: str, ml_bucket: str, run: str, dataset_dir: Path) -> dict:
    clips = curated_clips(s3, curated_bucket)
    if not clips:
        raise SystemExit(f"no clips under s3://{curated_bucket}/{PREFIX}")
    test = held_out_clips(dataset_dir)
    base = f"manifests/{run}/"

    # S3 refuses a body whose SHA-256 differs from the dataset manifest's.
    def put_test(clip):
        s3.put_object(Bucket=ml_bucket, Key=f"{base}test/{clip['path']}", Body=clip["source"].read_bytes(),
                      ChecksumSHA256=clip["sha256"])
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(put_test, test))

    manifest = {"snapshot": run, "bucket": curated_bucket, "prefix": PREFIX, "clips": clips,
                "test_clips": [{"path": c["path"], "sha256": c["sha256"]} for c in test]}
    sm_manifest = [{"prefix": f"s3://{curated_bucket}/{PREFIX}"}] + [c["key"][len(PREFIX):] for c in clips]
    s3.put_object(Bucket=ml_bucket, Key=f"{base}manifest.json", Body=json.dumps(manifest, indent=1).encode())
    s3.put_object(Bucket=ml_bucket, Key=f"{base}train.manifest", Body=json.dumps(sm_manifest).encode())
    return {"snapshot_uri": f"s3://{ml_bucket}/{base}", "manifest_uri": f"s3://{ml_bucket}/{base}manifest.json",
            "train_manifest_uri": f"s3://{ml_bucket}/{base}train.manifest", "num_clips": len(clips),
            "num_test_clips": len(test)}
