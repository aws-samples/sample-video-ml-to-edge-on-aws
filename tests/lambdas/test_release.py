# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import hashlib
import io
import json
import tarfile

import pytest

from conftest import ROOT, import_from
from fakes import FakeS3
from signing import FakeKms, LocalSigningKey

ENV = {"RELEASE_BUCKET": "releases", "SIGNING_KEY_ID": "arn:aws:kms:us-east-1:123456789012:key/test", "SITES": "factory-a,factory-b"}
ARN = "arn:aws:sagemaker:us-east-1:123456789012:model-package/conveyor-events/3"


def tarball(members: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


GOOD = tarball({n: b"{}" for n in ("model.onnx", "labels.json", "preprocess.py", "metrics.json")})


class FakeSageMaker:
    def __init__(self, status="Approved", sha256=None):
        self.status = status
        self.sha256 = sha256 or hashlib.sha256(GOOD).hexdigest()

    def describe_model_package(self, ModelPackageName):
        return {"ModelPackageArn": ModelPackageName, "ModelPackageVersion": 3, "ModelApprovalStatus": self.status,
                "InferenceSpecification": {"Containers": [{"ModelDataUrl": "s3://ml/training-output/job/output/model.tar.gz"}]},
                "CustomerMetadataProperties": {"artefact_version_id": "ver-7", "artefact_sha256": self.sha256}}


@pytest.fixture
def release(monkeypatch, tmp_path):
    module = import_from(ROOT / "lambdas" / "release", "handler", ENV)
    key = LocalSigningKey(tmp_path)
    fakes = {"s3": FakeS3({("ml", "training-output/job/output/model.tar.gz"): GOOD}), "kms": FakeKms(key),
             "sagemaker": FakeSageMaker()}
    for name, fake in fakes.items():
        monkeypatch.setattr(module, name, fake)
    return module, fakes, key


def event():
    return {"detail": {"ModelPackageArn": ARN, "ModelApprovalStatus": "Approved"}}


def test_publishes_signed_release_and_points_every_channel(release):
    module, fakes, _ = release
    result = module.main(event(), None)
    puts = fakes["s3"].puts
    body = puts[("releases", "releases/v3/release.json")]["Body"]
    doc = json.loads(body)
    assert doc["version"] == "v3" and doc["sha256"] == hashlib.sha256(GOOD).hexdigest()
    assert doc["model_package_arn"] == ARN and result["artefact"] == "releases/v3/model.tar.gz"
    assert puts[("releases", "releases/v3/model.tar.gz")]["Body"] == GOOD
    assert puts[("releases", "releases/v3/release.json.sig")]["Body"][0] == 0x30  # DER sequence
    for site in ("factory-a", "factory-b"):
        assert json.loads(puts[("releases", f"channels/{site}.json")]["Body"]) == {"version": "v3"}
    assert fakes["kms"].calls == [ENV["SIGNING_KEY_ID"]]


def test_package_no_longer_approved_is_not_released(release):
    module, fakes, _ = release
    fakes["sagemaker"].status = "Rejected"
    assert module.main(event(), None)["status"] == "Rejected"
    assert not fakes["s3"].puts


@pytest.mark.parametrize("members", [
    {"model.onnx": b"x", "labels.json": b"x", "preprocess.py": b"x"},
    {"model.onnx": b"x", "labels.json": b"x", "preprocess.py": b"x", "metrics.json": b"x", "../escape": b"x"},
])
def test_incomplete_or_unsafe_artefact_is_refused(release, members):
    module, fakes, _ = release
    fakes["s3"].objects[("ml", "training-output/job/output/model.tar.gz")] = tarball(members)
    with pytest.raises(ValueError):
        module.main(event(), None)
    assert not fakes["s3"].puts


def test_signs_only_the_registered_artefact_version(release):
    module, fakes, _ = release
    module.main(event(), None)
    assert fakes["s3"].downloads == [("ml", "training-output/job/output/model.tar.gz", {"VersionId": "ver-7"})]


def test_artefact_swapped_after_registration_is_refused(release):
    module, fakes, _ = release
    # The training role rewrote the object; the registered digest no longer matches.
    fakes["s3"].objects[("ml", "training-output/job/output/model.tar.gz")] = tarball(
        {n: b"evil" for n in ("model.onnx", "labels.json", "preprocess.py", "metrics.json")})
    with pytest.raises(ValueError, match="digest"):
        module.main(event(), None)
    assert not fakes["s3"].puts


def test_channels_move_only_after_the_signed_release_exists(release):
    module, fakes, _ = release
    module.main(event(), None)
    order = fakes["s3"].order
    last_release = max(order.index("releases/v3/release.json"), order.index("releases/v3/release.json.sig"))
    assert all(order.index(f"channels/{site}.json") > last_release for site in ("factory-a", "factory-b"))
