# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Validates a contributed clip once GuardDuty has scanned it.

Invoked by the EventBridge rule for "GuardDuty Malware Protection Object Scan
Result" events with scan result NO_THREATS_FOUND on the intake bucket. Reads the
scanned object version of intake/<site>/<label>/<uuid>.mp4, probes it, re-encodes
it to strip metadata, probes the copy, and writes it to
curated/<site>/<label>/<uuid>.mp4 with an S3 SHA-256 checksum. A rejected clip
gets rejected/<site>/<label>/<uuid>.json naming the reason; its bytes stay in the
intake bucket until the lifecycle rule expires them.

The scan result event can arrive before the object's tag is readable; the read
is then refused, the invocation fails, and Lambda's asynchronous retry succeeds.
"""

import json
import os
import re
import tempfile
from pathlib import Path

import boto3

from probe import probe
from reencode import reencode

INTAKE_BUCKET = os.environ["INTAKE_BUCKET"]
CURATED_BUCKET = os.environ["CURATED_BUCKET"]
SITES = set(os.environ["SITES"].split(","))
LABELS = set(os.environ["LABELS"].split(","))
KEY = re.compile(r"^intake/(?P<site>[a-z0-9-]+)/(?P<label>[a-z0-9-]+)/(?P<clip>[0-9a-f]{32})\.mp4$")

s3 = boto3.client("s3")


def parse_key(key: str):
    match = KEY.match(key)
    if not match or match["site"] not in SITES or match["label"] not in LABELS:
        return None
    return match["site"], match["label"], match["clip"]


def reject(site: str, label: str, clip: str, reason: str, info: dict) -> dict:
    record = {"clip": clip, "site": site, "label": label, "reason": reason, "probe": info}
    s3.put_object(Bucket=CURATED_BUCKET, Key=f"rejected/{site}/{label}/{clip}.json",
                  Body=json.dumps(record).encode(), ContentType="application/json")
    print(json.dumps({"event": "rejected", **record}))
    return record


def process(key: str, version_id: str | None) -> dict:
    parsed = parse_key(key)
    if parsed is None:
        print(json.dumps({"event": "ignored", "key": key}))
        return {"key": key, "reason": "unexpected-key"}
    site, label, clip = parsed
    with tempfile.TemporaryDirectory() as tmp:
        source, clean = Path(tmp) / "source.mp4", Path(tmp) / "clean.mp4"
        extra = {"VersionId": version_id} if version_id else None
        s3.download_file(INTAKE_BUCKET, key, str(source), ExtraArgs=extra)
        reason, info = probe(str(source))
        if reason:
            return reject(site, label, clip, reason, info)
        frames = reencode(str(source), str(clean), info["fps"])
        reason, clean_info = probe(str(clean))
        if reason or frames != info["decoded"]:
            return reject(site, label, clip, reason or "reencode-frame-mismatch", clean_info)
        curated_key = f"curated/{site}/{label}/{clip}.mp4"
        with clean.open("rb") as body:
            s3.put_object(Bucket=CURATED_BUCKET, Key=curated_key, Body=body, ContentType="video/mp4",
                          ChecksumAlgorithm="SHA256")
    print(json.dumps({"event": "curated", "key": curated_key, "frames": frames}))
    return {"key": curated_key, "frames": frames}


def main(event, _context):
    detail = event["detail"]
    obj = detail["s3ObjectDetails"]
    if obj["bucketName"] != INTAKE_BUCKET or detail["scanResultDetails"]["scanResultStatus"] != "NO_THREATS_FOUND":
        return {"skipped": obj.get("objectKey")}
    return process(obj["objectKey"], obj.get("versionId"))
