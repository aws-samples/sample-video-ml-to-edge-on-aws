# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Reports the caller's recent uploads and where each one is in the pipeline.

    GET /api/uploads

Answers with the caller's newest uploads in their site, newest first. It lists
intake/<site>/, which the intake lifecycle keeps for 7 days, and keeps only the
objects whose contributor=<sub> tag, signed into every upload by the presign
function, is the caller's. One request lists at most MAX_LISTED keys and reads
the owner tag of at most the MAX_TAGGED newest, so a contributor whose site
received that many newer clips from others sees none of their own. Clip names never reach AWS; the portal keeps them. Each
upload is reported as:
  accepted     curated/<site>/<label>/<clip>.mp4 exists
  rejected     rejected/<site>/<label>/<clip>.json exists (its reason), or the
               GuardDuty tag reports a threat or a failed scan
  validating   GuardDuty tagged the object NO_THREATS_FOUND, no verdict yet
  scanning     the object carries no GuardDuty tag yet
  unknown      the verdict could not be read (an S3 error other than not found)
"""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.exceptions import ClientError

INTAKE_BUCKET = os.environ["INTAKE_BUCKET"]
CURATED_BUCKET = os.environ["CURATED_BUCKET"]
SITES = set(os.environ["SITES"].split(","))
LABELS = set(os.environ["LABELS"].split(","))
MAX_UPLOADS = 20
# Bounds on the S3 calls of one request: keys listed, owner tags read.
MAX_LISTED = 5000
MAX_TAGGED = 100
# Owner tags are read concurrently: read one at a time, MAX_TAGGED of them take
# longer than the few seconds a clip spends scanning and validating.
TAG_READERS = 16
KEY = re.compile(r"^intake/[a-z0-9-]+/(?P<label>[a-z]+)/(?P<clip>[0-9a-f]{32})\.mp4$")
NOT_FOUND = ("404", "NoSuchKey", "NotFound")
SCAN_TAG = "GuardDutyMalwareScanStatus"
# What the validation function's reason codes mean to a contributor.
REASONS = {
    "codec-not-allowed": "not a supported video",
    "no-video-stream": "no video stream in the file",
    "not-decodable": "the video could not be decoded",
    "truncated": "the video is cut short",
    "too-large": "frames larger than 1920 pixels",
    "too-many-frames": "longer than 10,000 frames",
    "reencode-frame-mismatch": "the video could not be re-encoded cleanly",
}

s3 = boto3.client("s3")


def respond(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"content-type": "application/json"}, "body": json.dumps(body)}


def caller(event: dict) -> tuple[str | None, str | None]:
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    groups = claims.get("cognito:groups", [])
    if isinstance(groups, str):
        groups = groups.strip("[]").replace(",", " ").split()
    sites = set(groups) & SITES
    return claims.get("sub"), (sites.pop() if len(sites) == 1 else None)


def exists(bucket: str, key: str) -> bool:
    """Lists rather than heads the key, so the role needs no read on curated clips."""
    found = s3.list_objects_v2(Bucket=bucket, Prefix=key, MaxKeys=1).get("Contents", [])
    return bool(found) and found[0]["Key"] == key


def intake_tags(key: str) -> dict | None:
    try:
        tags = s3.get_object_tagging(Bucket=INTAKE_BUCKET, Key=key)["TagSet"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] in NOT_FOUND:
            return None
        raise
    return {t["Key"]: t["Value"] for t in tags}


def verdict(site: str, label: str, clip: str, tags: dict) -> dict:
    if exists(CURATED_BUCKET, f"curated/{site}/{label}/{clip}.mp4"):
        return {"state": "accepted"}
    try:
        record = s3.get_object(Bucket=CURATED_BUCKET, Key=f"rejected/{site}/{label}/{clip}.json")
        reason = json.loads(record["Body"].read())["reason"]
        return {"state": "rejected", "step": "validate", "reason": REASONS.get(reason, "failed validation")}
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in NOT_FOUND:
            raise
    scan = tags.get(SCAN_TAG)
    if scan is None:
        return {"state": "scanning"}
    if scan == "NO_THREATS_FOUND":
        return {"state": "validating"}
    reason = "malware found" if scan == "THREATS_FOUND" else "the malware scan could not complete"
    return {"state": "rejected", "step": "scan", "reason": reason}


def site_objects(site: str) -> list[dict]:
    objects, more = [], {}
    while len(objects) < MAX_LISTED:
        page = s3.list_objects_v2(Bucket=INTAKE_BUCKET, Prefix=f"intake/{site}/",
                                 MaxKeys=MAX_LISTED - len(objects), **more)
        objects += page.get("Contents", [])
        if not page.get("IsTruncated"):
            break
        more = {"ContinuationToken": page["NextContinuationToken"]}
    return objects


def log_error(key: str, exc: ClientError) -> None:
    print(json.dumps({"event": "status-error", "key": key, "code": exc.response["Error"]["Code"]}))


def owner_tags(key: str) -> dict | None:
    try:
        return intake_tags(key)
    except ClientError as exc:
        # Without the owner tag the clip cannot be shown to anyone.
        log_error(key, exc)
        return None


def recent_uploads(sub: str, site: str) -> list[dict]:
    newest = sorted(site_objects(site), key=lambda o: o["LastModified"], reverse=True)[:MAX_TAGGED]
    clips = [(obj, match) for obj in newest
             if (match := KEY.match(obj["Key"])) and match["label"] in LABELS]
    with ThreadPoolExecutor(TAG_READERS) as pool:
        tag_sets = list(pool.map(owner_tags, [obj["Key"] for obj, _ in clips]))
    uploads = []
    for (obj, match), tags in zip(clips, tag_sets):
        if tags is None or tags.get("contributor") != sub:
            continue
        label, clip = match["label"], match["clip"]
        try:
            state = verdict(site, label, clip, tags)
        except ClientError as exc:
            log_error(obj["Key"], exc)
            state = {"state": "unknown"}
        uploads.append({"clip": clip, "label": label, "uploaded": obj["LastModified"].isoformat(), **state})
        if len(uploads) == MAX_UPLOADS:
            break
    return uploads


def main(event, _context):
    sub, site = caller(event)
    if not sub or not site:
        return respond(403, {"error": "caller must belong to exactly one site group"})
    return respond(200, {"site": site, "uploads": recent_uploads(sub, site)})
