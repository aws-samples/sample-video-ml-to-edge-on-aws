# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Runs the shipped site/bin/fetch_release.sh against a fake `aws`, `setpriv` and
`systemctl` on PATH and a release bucket on disk. Needs GNU coreutils and flock (Linux)."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from conftest import ROOT
from signing import LocalSigningKey

FAKE_AWS = """#!/usr/bin/env bash
# aws s3 cp s3://<bucket>/<key> <dest> ...: copies from $FAKE_S3/<bucket>/<key>.
set -euo pipefail
[[ "$1 $2" == "s3 cp" ]] || { echo "unexpected aws call: $*" >&2; exit 2; }
src="$FAKE_S3/${3#s3://}"
[[ -f "$src" ]] || { echo "NoSuchKey: $3" >&2; exit 1; }
cp "$src" "$4"
"""
# Logs the identity it was asked to drop to, then runs the command as the test user.
FAKE_SETPRIV = """#!/usr/bin/env bash
echo "$*" >> "$SETPRIV_LOG"
while [[ "$1" == --* ]]; do shift; done
exec "$@"
"""
# Fails on a release whose model.onnx says so.
SELFTEST_STUB = """import json, pathlib, sys
model = pathlib.Path(sys.argv[1])
if (model / "model.onnx").read_bytes() == b"broken":
    sys.exit("classifier failed to load model.onnx")
print(json.dumps({"stub": True, "model": str(model)}))
"""


def model_tarball(marker: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("model.onnx")
        info.size = len(marker)
        tar.addfile(info, io.BytesIO(marker))
    return buf.getvalue()


@pytest.fixture
def site(tmp_path):
    base, s3, fakebin = tmp_path / "conveyor", tmp_path / "s3" / "rel", tmp_path / "fakebin"
    (base / "gateway").mkdir(parents=True)
    shutil.copytree(ROOT / "site" / "bin", base / "bin")
    (base / "gateway" / "selftest.py").write_text(SELFTEST_STUB)
    (base / "env").write_text("SITE=factory-a\nRELEASE_BUCKET=rel\nREGION=eu-west-1\n")  # pragma: allowlist secret
    key = LocalSigningKey(tmp_path)
    shutil.copyfile(key.public, base / "release-public-key.pem")
    fakebin.mkdir()
    (fakebin / "aws").write_text(FAKE_AWS)
    (fakebin / "setpriv").write_text(FAKE_SETPRIV)
    (fakebin / "systemctl").write_text(f"#!/usr/bin/env bash\necho \"$*\" >> {tmp_path}/systemctl.log\n")
    for tool in fakebin.iterdir():
        tool.chmod(0o755)
    env = {**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}", "FAKE_S3": str(tmp_path / "s3"),
           "SETPRIV_LOG": str(tmp_path / "setpriv.log")}

    def publish(version, marker=b"model", signer=key, channel=None, tamper=False):
        artefact = model_tarball(marker)
        release = {"version": version, "artefact": f"releases/{version}/model.tar.gz",
                   "sha256": hashlib.sha256(artefact).hexdigest()}
        body = (json.dumps(release, indent=1, sort_keys=True) + "\n").encode()
        folder = s3 / "releases" / version
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "model.tar.gz").write_bytes(artefact + (b"x" if tamper else b""))
        (folder / "release.json").write_bytes(body)
        (folder / "release.json.sig").write_bytes(signer.sign(body))
        (s3 / "channels").mkdir(exist_ok=True)
        (s3 / "channels" / "factory-a.json").write_text(json.dumps({"version": channel or version}))

    def fetch():
        return subprocess.run(["bash", str(base / "bin" / "fetch_release.sh")], env=env, capture_output=True, text=True)

    def state():
        return json.loads((base / "state" / "fetch.json").read_text())

    return {"base": base, "publish": publish, "fetch": fetch, "state": state, "tmp": tmp_path}


def installed(base: Path):
    link = base / "model"
    return os.readlink(link) if link.is_symlink() else None


def test_good_release_is_installed_self_tested_and_ui_restarted(site):
    site["publish"]("v2", marker=b"two")
    result = site["fetch"]()
    assert result.returncode == 0, result.stderr
    assert installed(site["base"]).endswith("model-v2")
    assert (site["base"] / "model" / "model.onnx").read_bytes() == b"two"
    assert site["state"]()["status"] == "verified"
    assert json.loads((site["base"] / "state" / "selftest.json").read_text())["model"].endswith("model-v2")
    assert "restart conveyor-ui.service" in (site["tmp"] / "systemctl.log").read_text()


def test_the_self_test_runs_as_conveyor_without_new_privileges(site):
    site["publish"]("v2")
    assert site["fetch"]().returncode == 0
    flags = (site["tmp"] / "setpriv.log").read_text().split()
    assert {"--reuid=conveyor", "--regid=conveyor", "--init-groups", "--no-new-privs"} <= set(flags)
    assert flags[flags.index("--no-new-privs") + 1] == "python3.12"


def test_a_failing_self_test_keeps_the_running_model_and_is_retried(site):
    site["publish"]("v2", marker=b"two")
    assert site["fetch"]().returncode == 0
    (site["tmp"] / "systemctl.log").unlink()
    site["publish"]("v3", marker=b"broken")
    result = site["fetch"]()
    assert result.returncode == 1 and "failed to load" in result.stderr
    assert installed(site["base"]).endswith("model-v2")
    assert (site["base"] / "model" / "model.onnx").read_bytes() == b"two"
    assert not (site["base"] / "model-v3").exists()
    assert site["state"]()["status"] == "rejected" and "self-test failed" in site["state"]()["detail"]
    assert json.loads((site["base"] / "state" / "selftest.json").read_text())["model"].endswith("model-v2")
    assert not (site["tmp"] / "systemctl.log").exists()
    second = site["fetch"]()
    assert second.returncode == 1 and "already installed" not in second.stdout
    site["publish"]("v4", marker=b"four")
    assert site["fetch"]().returncode == 0
    assert installed(site["base"]).endswith("model-v4") and site["state"]()["status"] == "verified"


def test_tampered_artefact_is_not_installed(site):
    site["publish"]("v2", tamper=True)
    assert site["fetch"]().returncode == 1
    assert installed(site["base"]) is None and site["state"]()["status"] == "rejected"
    assert not (site["base"] / "model-v2").exists()


def test_release_signed_by_another_key_is_not_installed(site):
    other = site["tmp"] / "other"
    other.mkdir()
    site["publish"]("v2", signer=LocalSigningKey(other))
    assert site["fetch"]().returncode == 1
    assert installed(site["base"]) is None and "signature" in site["state"]()["detail"]


@pytest.mark.parametrize("version", ["../x", "v2/../../etc", "2", "v2a"])
def test_bad_version_string_is_refused_before_any_download(site, version):
    site["publish"]("v2", channel=version)
    (site["base"] / "model-x").mkdir()
    assert site["fetch"]().returncode == 1
    assert site["state"]()["status"] == "rejected" and (site["base"] / "model-x").exists()


def test_older_release_is_refused_and_the_installed_one_kept(site):
    site["publish"]("v3", marker=b"three")
    assert site["fetch"]().returncode == 0
    site["publish"]("v2", marker=b"two")
    assert site["fetch"]().returncode == 1
    assert installed(site["base"]).endswith("model-v3") and "older" in site["state"]()["detail"]


def test_same_release_is_not_reinstalled(site):
    site["publish"]("v2")
    assert site["fetch"]().returncode == 0
    assert "already installed" in site["fetch"]().stdout


def test_restoring_the_channel_after_a_refusal_clears_the_refused_state(site):
    site["publish"]("v2", marker=b"two")
    assert site["fetch"]().returncode == 0
    other = site["tmp"] / "other"
    other.mkdir()
    site["publish"]("v3", signer=LocalSigningKey(other))
    assert site["fetch"]().returncode == 1 and site["state"]()["status"] == "rejected"
    site["publish"]("v2", marker=b"two")
    assert site["fetch"]().returncode == 0
    assert site["state"]() | {"checked_at": None} == {"version": "v2", "status": "verified",
                                                      "detail": "release v2 already installed", "checked_at": None}
    assert installed(site["base"]).endswith("model-v2")


def test_no_channel_yet_is_a_normal_wait_not_a_failure(site):
    assert site["fetch"]().returncode == 0
    assert site["state"]()["status"] == "waiting" and installed(site["base"]) is None
