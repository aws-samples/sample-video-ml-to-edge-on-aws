# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Downloads the sample dataset archive, refuses it unless its SHA-256 is the
pinned one, extracts it and verifies every clip against the SHA-256 recorded in
its manifest.json.

    python scripts/fetch_dataset.py [archive-url archive-sha256] [dest-dir]

The archive holds manifest.json and <site>/<split>/<label>/*.mp4. The train and
val splits are what contributors upload (scripts/upload_clips.py); the test split
holds held-out clips to try in the gateway UI. Exits 1 when a file is missing or
its digest differs.
"""

import hashlib
import json
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASET_URL = "https://github.com/aws-samples/sample-video-ml-to-edge-on-aws/releases/download/dataset-v1/conveyor-dataset.tar.gz"
# The manifest inside the archive cannot vouch for the archive itself.
UNPUBLISHED = "set-at-publication"
DATASET_SHA256 = UNPUBLISHED


def verify(dest: Path) -> list[str]:
    manifest = json.loads((dest / "manifest.json").read_text())
    problems = []
    for entry in manifest["files"]:
        path = dest / entry["path"]
        if not path.is_file():
            problems.append(f"missing {entry['path']}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            problems.append(f"digest mismatch {entry['path']}")
    return problems


def fetch(url: str, sha256: str, dest: Path) -> list[str]:
    if urllib.parse.urlsplit(url).scheme != "https":
        raise SystemExit(f"refusing a dataset URL that is not https: {url}")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "dataset.tar.gz"
        digest = hashlib.sha256()
        with urllib.request.urlopen(url, timeout=60) as response, archive.open("wb") as out:  # nosemgrep: dynamic-urllib-use-detected - https only, checked above # nosec B310
            while chunk := response.read(1 << 20):
                digest.update(chunk)
                out.write(chunk)
        if digest.hexdigest() != sha256:
            raise SystemExit(f"refusing the archive: its SHA-256 is {digest.hexdigest()}, not {sha256}")
        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tar:
            tar.extractall(dest, filter="data")
    return verify(dest)


def main() -> int:
    args = sys.argv[1:]
    if len(args) not in (0, 2, 3):
        raise SystemExit(__doc__)
    url, sha256 = args[:2] if args else (DATASET_URL, DATASET_SHA256)
    if sha256 == UNPUBLISHED:
        raise SystemExit("the dataset-v1 asset is not published yet: pass an archive URL and its SHA-256")
    dest = Path(args[2]) if len(args) > 2 else ROOT / "data" / "conveyor"
    problems = fetch(url, sha256, dest)
    for problem in problems:
        print(problem)
    files = len(json.loads((dest / "manifest.json").read_text())["files"])
    print(f"{dest}: {files} files, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
