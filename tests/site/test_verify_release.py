# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Round trip: the release Lambda publishes with a local stand-in for the KMS key,
and the gateway's shipped verifier checks what it wrote."""

import json
import subprocess

import pytest

from conftest import ROOT
from signing import LocalSigningKey
from test_release import ARN, GOOD, event, release  # noqa: F401

VERIFY = ROOT / "site" / "bin" / "verify_release.sh"


@pytest.fixture
def published(release, tmp_path):  # noqa: F811
    module, fakes, key = release
    module.main(event(), None)
    files = {}
    for name in ("release.json", "release.json.sig", "model.tar.gz"):
        files[name] = tmp_path / name
        files[name].write_bytes(fakes["s3"].puts[("releases", f"releases/v3/{name}")]["Body"])
    return files, key, tmp_path


def verify(files, public, version="v3"):
    return subprocess.run(["bash", str(VERIFY), str(files["release.json"]), str(files["release.json.sig"]),
                           str(public), str(files["model.tar.gz"]), version], capture_output=True, text=True)


def test_published_release_verifies(published):
    files, key, _ = published
    result = verify(files, key.public)
    assert result.returncode == 0, result.stderr


def test_tampered_artefact_fails(published):
    files, key, _ = published
    files["model.tar.gz"].write_bytes(GOOD + b"x")
    result = verify(files, key.public)
    assert result.returncode == 1 and "sha256 mismatch" in result.stderr


def test_rewritten_release_json_fails_signature(published):
    files, key, _ = published
    # An attacker with bucket write access swaps in a new artefact and its digest.
    files["model.tar.gz"].write_bytes(b"evil")
    doc = json.loads(files["release.json"].read_text())
    doc["sha256"] = __import__("hashlib").sha256(b"evil").hexdigest()
    files["release.json"].write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    result = verify(files, key.public)
    assert result.returncode == 1 and "signature verification failed" in result.stderr


def test_signature_from_another_key_fails(published):
    files, _, tmp_path = published
    other = tmp_path / "other"
    other.mkdir()
    result = verify(files, LocalSigningKey(other).public)
    assert result.returncode == 1 and "signature verification failed" in result.stderr


def test_replayed_older_release_under_new_version_fails(published):
    files, key, _ = published
    result = verify(files, key.public, version="v4")
    assert result.returncode == 1 and "expected v4" in result.stderr
