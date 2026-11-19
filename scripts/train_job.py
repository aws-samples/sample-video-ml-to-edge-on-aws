# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Snapshots the curated clips and the local dataset's held-out test split, and
trains tiny3d on them with a managed Spot SageMaker training job.

    python scripts/train_job.py [dataset-dir]

dataset-dir defaults to data/conveyor, where scripts/fetch_dataset.py puts the
dataset. Checks first that the account's Spot training quota for the instance type
is at least 1 and prints the request command when it is not. Then follows the job
until it ends. When it completes, the registration function in the ConveyorMl
stack registers the model as a package awaiting manual approval, whether or not
this script is still running.
"""

import io
import json
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snapshot  # noqa: E402
from stack_outputs import outputs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCES = sorted((ROOT / "ml" / "train").glob("*.py")) + [ROOT / "ml" / "train" / "requirements.txt",
                                                          ROOT / "shared" / "preprocess.py"]
TRAINING_IMAGE = "pytorch-training:2.9.0-gpu-py312"
POLL_SECONDS = 30
INSTANCE_TYPE = "ml.g4dn.xlarge"
# Service Quotas code of "ml.g4dn.xlarge for spot training job usage".
SPOT_QUOTA_CODE = "L-944F78BB"


def sourcedir() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in SOURCES:
            tar.add(path, arcname=path.name)
    return buf.getvalue()


def image(registry: str, region: str, name: str) -> str:
    return f"{registry}.dkr.ecr.{region}.amazonaws.com/{name}"


def check_spot_quota(session) -> None:
    quotas = session.client("service-quotas")
    try:
        value = quotas.get_service_quota(ServiceCode="sagemaker", QuotaCode=SPOT_QUOTA_CODE)["Quota"]["Value"]
    except quotas.exceptions.NoSuchResourceException:
        value = quotas.get_aws_default_service_quota(ServiceCode="sagemaker", QuotaCode=SPOT_QUOTA_CODE)["Quota"]["Value"]
    if value < 1:
        raise SystemExit(
            f"the Spot training quota for {INSTANCE_TYPE} is {value:g}; request one instance with:\n"
            f"  aws service-quotas request-service-quota-increase --region {session.region_name} "
            f"--service-code sagemaker --quota-code {SPOT_QUOTA_CODE} --desired-value 1")


def training_request(job: str, region: str, ml: dict, code_uri: str, snap: dict) -> dict:
    s3_input = lambda name, kind, uri: {  # noqa: E731
        "ChannelName": name, "InputMode": "File",
        "DataSource": {"S3DataSource": {"S3DataType": kind, "S3Uri": uri, "S3DataDistributionType": "FullyReplicated"}},
    }
    return {
        "TrainingJobName": job,
        "AlgorithmSpecification": {
            "TrainingImage": image(ml["DlcRegistry"], region, TRAINING_IMAGE), "TrainingInputMode": "File",
            "MetricDefinitions": [{"Name": "val_accuracy", "Regex": "val_accuracy=([0-9.]+)"},
                                  {"Name": "train_loss", "Regex": "train_loss=([0-9.]+)"},
                                  {"Name": "test_accuracy", "Regex": "test_accuracy=([0-9.]+)"}],
        },
        "RoleArn": ml["TrainingRoleArn"],
        "HyperParameters": {
            "sagemaker_program": json.dumps("train.py"),
            "sagemaker_submit_directory": json.dumps(code_uri),
            "sagemaker_region": json.dumps(region),
        },
        "InputDataConfig": [s3_input("train", "ManifestFile", snap["train_manifest_uri"]),
                            s3_input("snapshot", "S3Prefix", snap["snapshot_uri"])],
        "OutputDataConfig": {"S3OutputPath": f"s3://{ml['MlBucket']}/training-output/", "KmsKeyId": ml["MlBucketKeyArn"]},
        "ResourceConfig": {"InstanceType": INSTANCE_TYPE, "InstanceCount": 1, "VolumeSizeInGB": 30},
        # Managed Spot: the job restarts from scratch if interrupted, which costs
        # minutes for a model this small, so no checkpointing.
        "EnableManagedSpotTraining": True,
        "StoppingCondition": {"MaxRuntimeInSeconds": 3600, "MaxWaitTimeInSeconds": 7200},
    }


def wait(sm, job: str) -> dict:
    last = None
    while True:
        desc = sm.describe_training_job(TrainingJobName=job)
        if desc.get("SecondaryStatus") != last:
            last = desc.get("SecondaryStatus")
            print(f"{datetime.now(timezone.utc):%H:%M:%S} {desc['TrainingJobStatus']} {last}", flush=True)
        if desc["TrainingJobStatus"] in ("Completed", "Failed", "Stopped"):
            return desc
        time.sleep(POLL_SECONDS)  # nosemgrep: arbitrary-sleep - polls the training job status at a fixed interval


def main() -> int:
    if len(sys.argv) > 2:
        raise SystemExit(__doc__)
    dataset_dir = Path(sys.argv[1]) if len(sys.argv) == 2 else ROOT / "data" / "conveyor"
    session = boto3.Session()
    check_spot_quota(session)
    region = session.region_name
    s3, sm = session.client("s3"), session.client("sagemaker")
    intake, ml = outputs(session, "ConveyorIntake"), outputs(session, "ConveyorMl")
    job = "tiny3d-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    print(f"training_job={job}", flush=True)

    code_key = f"code/{job}/sourcedir.tar.gz"
    s3.put_object(Bucket=ml["MlBucket"], Key=code_key, Body=sourcedir())
    snap = snapshot.build(s3, intake["CuratedBucket"], ml["MlBucket"], job, dataset_dir)
    print(f"snapshot={snap['manifest_uri']} clips={snap['num_clips']} test_clips={snap['num_test_clips']}", flush=True)

    sm.create_training_job(**training_request(job, region, ml, f"s3://{ml['MlBucket']}/{code_key}", snap))
    desc = wait(sm, job)
    if desc["TrainingJobStatus"] != "Completed":
        print(f"training {desc['TrainingJobStatus']}: {desc.get('FailureReason', '')}", file=sys.stderr)
        return 1
    test_accuracy = {m["MetricName"]: m["Value"] for m in desc.get("FinalMetricDataList", [])}.get("test_accuracy")
    print(f"test_accuracy={test_accuracy}; the registration function registers the model as PendingManualApproval.")
    print(f"find it with:\n  aws sagemaker list-model-packages --model-package-group-name {ml['ModelPackageGroup']} "
          "--sort-by CreationTime --sort-order Descending --query 'ModelPackageSummaryList[0].[ModelPackageArn,ModelApprovalStatus]' --output text")
    return 0


if __name__ == "__main__":
    sys.exit(main())
