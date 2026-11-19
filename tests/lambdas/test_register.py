# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import hashlib
import io
import json
import tarfile
from datetime import datetime, timedelta, timezone

import pytest

from conftest import ROOT, import_from

ROLE = "arn:aws:iam::123456789012:role/ConveyorMl-TrainingRole"
ENV = {"MODEL_PACKAGE_GROUP": "conveyor-events", "TRAINING_ROLE_ARN": ROLE,
       "INFERENCE_IMAGE": "763104351884.dkr.ecr.us-east-1.amazonaws.com/pytorch-inference:2.6.0-cpu-py312"}
END = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
URI = "s3://ml/training-output/tiny3d-20260101-110000/output/model.tar.gz"
METRICS = {"test_accuracy": 0.9781, "num_test": 320, "selection_val_accuracy": 0.9937, "snapshot": "tiny3d-20260101-110000"}


def tarball(members: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


ARTEFACT = tarball({"model.onnx": b"onnx", "metrics.json": json.dumps(METRICS).encode()})


class FakeS3:
    def __init__(self, body=ARTEFACT, modified=END - timedelta(seconds=5)):
        self.body, self.modified = body, modified

    def head_object(self, Bucket, Key):
        assert (Bucket, Key) == ("ml", URI.removeprefix("s3://ml/"))
        return {"LastModified": self.modified, "VersionId": "ver-1"}

    def get_object(self, Bucket, Key, VersionId):
        assert VersionId == "ver-1"
        return {"Body": io.BytesIO(self.body)}


class FakeSageMaker:
    def __init__(self, status="Completed", role=ROLE):
        self.status, self.role, self.created = status, role, []

    def describe_training_job(self, TrainingJobName):
        return {"TrainingJobName": TrainingJobName, "TrainingJobStatus": self.status, "RoleArn": self.role,
                "ModelArtifacts": {"S3ModelArtifacts": URI}, "TrainingEndTime": END,
                # The last epoch's validation accuracy, which is not the shipped model's.
                "FinalMetricDataList": [{"MetricName": "val_accuracy", "Value": 0.5}]}

    def create_model_package(self, **request):
        self.created.append(request)
        return {"ModelPackageArn": "arn:aws:sagemaker:us-east-1:123456789012:model-package/conveyor-events/7"}


@pytest.fixture
def register(monkeypatch):
    module = import_from(ROOT / "lambdas" / "register", "handler", ENV)
    fakes = {"s3": FakeS3(), "sagemaker": FakeSageMaker()}
    for name, fake in fakes.items():
        monkeypatch.setattr(module, name, fake)
    return module, fakes


def event(job="tiny3d-20260101-110000"):
    return {"detail": {"TrainingJobName": job, "TrainingJobStatus": "Completed"}}


def test_registers_pending_approval_with_the_test_accuracy_from_the_artefact(register):
    module, fakes = register
    result = module.main(event(), None)
    [request] = fakes["sagemaker"].created
    assert request["ModelApprovalStatus"] == "PendingManualApproval"
    assert request["ModelPackageGroupName"] == "conveyor-events"
    meta = request["CustomerMetadataProperties"]
    assert meta["test_accuracy"] == "0.9781" and meta["num_test"] == "320"
    assert meta["selection_val_accuracy"] == "0.9937" and "val_accuracy" not in meta
    assert meta["artefact_version_id"] == "ver-1" and meta["artefact_sha256"] == hashlib.sha256(ARTEFACT).hexdigest()
    assert request["InferenceSpecification"]["Containers"] == [{"Image": ENV["INFERENCE_IMAGE"], "ModelDataUrl": URI}]
    assert result["model_package_arn"].endswith("/conveyor-events/7") and result["test_accuracy"] == 0.9781


def test_job_name_is_the_idempotency_token(register):
    module, fakes = register
    module.main(event(), None)
    assert fakes["sagemaker"].created[0]["ClientToken"] == "tiny3d-20260101-110000"


def test_output_rewritten_after_the_job_is_refused(register):
    module, fakes = register
    fakes["s3"].modified = END + timedelta(minutes=3)
    with pytest.raises(ValueError, match="changed after"):
        module.main(event(), None)
    assert not fakes["sagemaker"].created


@pytest.mark.parametrize("status, role", [("Stopped", ROLE), ("Completed", "arn:aws:iam::123456789012:role/other")])
def test_job_not_completed_by_the_sample_training_role_is_skipped(register, status, role):
    module, fakes = register
    fakes["sagemaker"].status, fakes["sagemaker"].role = status, role
    assert module.main(event(), None)["skipped"] == "tiny3d-20260101-110000"
    assert not fakes["sagemaker"].created


def test_artefact_without_metrics_is_refused(register):
    module, fakes = register
    fakes["s3"].body = tarball({"model.onnx": b"onnx"})
    with pytest.raises(ValueError, match="metrics.json"):
        module.main(event(), None)
    assert not fakes["sagemaker"].created
