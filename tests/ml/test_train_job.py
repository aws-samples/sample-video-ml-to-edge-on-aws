# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import pytest

from conftest import ROOT, import_from

train_job = import_from(ROOT / "scripts", "train_job")
ML = {"DlcRegistry": "763104351884", "TrainingRoleArn": "arn:aws:iam::123456789012:role/ConveyorMl-TrainingRole",
      "MlBucket": "ml", "MlBucketKeyArn": "arn:aws:kms:eu-west-1:123456789012:key/k"}
SNAP = {"train_manifest_uri": "s3://ml/manifests/run-1/train.manifest", "snapshot_uri": "s3://ml/manifests/run-1/"}


def test_job_reads_the_curated_clips_and_the_snapshot_with_its_test_clips():
    request = train_job.training_request("tiny3d-1", "eu-west-1", ML, "s3://ml/code/x.tar.gz", SNAP)
    channels = {c["ChannelName"]: c["DataSource"]["S3DataSource"] for c in request["InputDataConfig"]}
    assert channels["train"] == {"S3DataType": "ManifestFile", "S3Uri": SNAP["train_manifest_uri"], "S3DataDistributionType": "FullyReplicated"}
    assert channels["snapshot"]["S3DataType"] == "S3Prefix" and channels["snapshot"]["S3Uri"] == SNAP["snapshot_uri"]


def test_test_accuracy_is_a_training_job_metric_and_val_accuracy_stays():
    request = train_job.training_request("tiny3d-1", "eu-west-1", ML, "s3://ml/code/x.tar.gz", SNAP)
    names = {m["Name"]: m["Regex"] for m in request["AlgorithmSpecification"]["MetricDefinitions"]}
    assert names["test_accuracy"] == "test_accuracy=([0-9.]+)" and "val_accuracy" in names


class FakeQuotas:
    class exceptions:
        class NoSuchResourceException(Exception):
            pass

    def __init__(self, applied=None, default=0.0):
        self.applied, self.default = applied, default

    def get_service_quota(self, ServiceCode, QuotaCode):
        if self.applied is None:
            raise self.exceptions.NoSuchResourceException()
        return {"Quota": {"Value": self.applied}}

    def get_aws_default_service_quota(self, ServiceCode, QuotaCode):
        return {"Quota": {"Value": self.default}}


class FakeSession:
    region_name = "eu-west-1"

    def __init__(self, quotas):
        self.quotas = quotas

    def client(self, name):
        assert name == "service-quotas"
        return self.quotas


def test_zero_spot_quota_stops_before_any_write_with_the_request_command():
    with pytest.raises(SystemExit, match="request-service-quota-increase .* --quota-code L-944F78BB --desired-value 1"):
        train_job.check_spot_quota(FakeSession(FakeQuotas(applied=None, default=0.0)))


def test_applied_quota_of_one_passes():
    train_job.check_spot_quota(FakeSession(FakeQuotas(applied=1.0)))
