# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Issues a presigned PUT URL for one MP4 clip at intake/<site>/<label>/<uuid>.mp4.

The site comes from the caller's Cognito group, never from the request, so a
contributor can only add clips to their own site. The label must be on the
allowlist. The declared size is signed into the URL as Content-Length, so S3
refuses a body of any other length. The caller's Cognito sub is signed in as the
object tag contributor=<sub>, which the status route uses to show contributors
their own uploads only. The contributor's filename never reaches AWS.
"""

import json
import os
import uuid

import boto3
from botocore.config import Config

BUCKET = os.environ["INTAKE_BUCKET"]
LABELS = set(os.environ["LABELS"].split(","))
SITES = set(os.environ["SITES"].split(","))
MAX_BYTES = int(os.environ["MAX_BYTES"])
EXPIRES_IN = 900
CONTENT_TYPE = "video/mp4"

s3 = boto3.client("s3", config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))


def respond(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"content-type": "application/json"}, "body": json.dumps(body)}


def parse_body(event: dict) -> dict:
    raw = event.get("body") or ""
    body = json.loads(raw) if raw else {}
    if not isinstance(body, dict):
        raise ValueError("body must be a JSON object")
    return body


def claims_of(event: dict) -> dict:
    return event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})


def caller_groups(event: dict) -> set[str]:
    """cognito:groups as the HTTP API JWT authorizer passes it: a list, or a string
    such as "[factory-a]"."""
    groups = claims_of(event).get("cognito:groups", [])
    if isinstance(groups, str):
        groups = groups.strip("[]").replace(",", " ").split()
    return set(groups)


def declared_size(body: dict):
    size = body.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_BYTES:
        return None
    return size


def main(event, _context):
    sites = caller_groups(event) & SITES
    if len(sites) != 1:
        return respond(403, {"error": "caller must belong to exactly one site group"})
    site = sites.pop()
    try:
        body = parse_body(event)
    except ValueError:
        return respond(400, {"error": "body must be a JSON object"})
    label = body.get("label")
    if label not in LABELS:
        return respond(400, {"error": "label not in allowlist", "labels": sorted(LABELS)})
    size = declared_size(body)
    if size is None:
        return respond(400, {"error": f"size must be an integer from 1 to {MAX_BYTES} bytes"})

    clip_id = uuid.uuid4().hex
    key = f"intake/{site}/{label}/{clip_id}.mp4"
    claims = claims_of(event)
    tagging = f"contributor={claims['sub']}"
    url = s3.generate_presigned_url(
        "put_object", ExpiresIn=EXPIRES_IN,
        Params={"Bucket": BUCKET, "Key": key, "ContentType": CONTENT_TYPE, "ContentLength": size, "Tagging": tagging},
    )
    # With S3 data events off, this line is what ties an upload to a contributor.
    print(json.dumps({"event": "presign", "user": claims.get("sub"), "username": claims.get("cognito:username"),
                      "site": site, "label": label, "clip": clip_id, "size": size}))
    # The browser must send exactly these headers: all of them are signed.
    headers = {"Content-Type": CONTENT_TYPE, "x-amz-tagging": tagging}
    return respond(200, {"url": url, "key": key, "clipId": clip_id, "label": label, "headers": headers,
                         "expiresIn": EXPIRES_IN})
