# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Contributes a site's clips from a local dataset through the portal API, the
way a contributor's browser does: Cognito sign-in, presign, PUT.

    PORTAL_PASSWORD=... python scripts/upload_clips.py <dataset-dir> <username>

The dataset directory holds manifest.json and <site>/<split>/<label>/*.mp4. Only
train and val clips of the contributor's own site are sent; the presign API would place any
clip under that site regardless.
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stack_outputs import outputs  # noqa: E402


def sign_in(client_id: str, username: str, password: str) -> str:
    cognito = boto3.client("cognito-idp")
    result = cognito.initiate_auth(ClientId=client_id, AuthFlow="USER_PASSWORD_AUTH",
                                   AuthParameters={"USERNAME": username, "PASSWORD": password})
    if "AuthenticationResult" not in result:
        sys.exit(f"sign-in needs {result.get('ChallengeName')}; sign in once in the portal first")
    return result["AuthenticationResult"]["IdToken"]


def site_of(token: str) -> str:
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    groups = claims.get("cognito:groups", [])
    if len(groups) != 1:
        sys.exit(f"user must be in exactly one site group, is in {groups}")
    return groups[0]


def upload(portal: str, token: str, path: Path, label: str) -> str:
    """Presigns and PUTs one clip, retrying twice on a dropped connection."""
    for attempt in range(3):
        try:
            return upload_once(portal, token, path, label)
        except urllib.error.URLError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def https(url: str) -> str:
    if urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError(f"refusing a URL that is not https: {url}")
    return url


def upload_once(portal: str, token: str, path: Path, label: str) -> str:
    request = urllib.request.Request(https(f"{portal}/api/presign"), method="POST",
                                     data=json.dumps({"label": label, "size": path.stat().st_size}).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": token})
    with urllib.request.urlopen(request, timeout=30) as response:  # nosemgrep: dynamic-urllib-use-detected - the stack's own HTTPS URL # nosec B310
        grant = json.load(response)
    # Every returned header is signed into the URL; S3 refuses the PUT without them.
    put = urllib.request.Request(https(grant["url"]), method="PUT", data=path.read_bytes(), headers=grant["headers"])
    with urllib.request.urlopen(put, timeout=120) as response:  # nosemgrep: dynamic-urllib-use-detected - presigned S3 HTTPS URL # nosec B310
        response.read()
    return grant["key"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("username")
    args = parser.parse_args()
    intake = outputs(boto3.Session(), "ConveyorIntake")
    token = sign_in(intake["UserPoolClientId"], args.username, os.environ["PORTAL_PASSWORD"])
    site = site_of(token)
    manifest = json.loads((args.dataset / "manifest.json").read_text())
    files = [f for f in manifest["files"] if f["site"] == site and f["split"] in ("train", "val")]
    portal = intake["PortalUrl"].rstrip("/")
    with ThreadPoolExecutor(max_workers=8) as pool:
        keys = pool.map(lambda f: upload(portal, token, args.dataset / f["path"], f["label"]), files)
        for n, (f, key) in enumerate(zip(files, keys), 1):
            print(f"{n}/{len(files)} {f['path']} -> {key}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
