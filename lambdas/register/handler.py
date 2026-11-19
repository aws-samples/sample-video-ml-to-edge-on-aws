# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Registers a completed training job's model as a package awaiting manual approval.

Invoked by the EventBridge rule for "SageMaker Training Job State Change" events
with TrainingJobStatus Completed for tiny3d-* jobs. Re-reads the job and acts only
on a completed job run by the sample's training role. Pins the job's model.tar.gz:
its object version and SHA-256, refusing an object changed after the job ended,
since the training role can write any job's output; the release function later
signs only that version and only if the digest still holds. Registers it in the
model package group with the test accuracy from the artefact's metrics.json, the
score of the shipped model on clips that took no part in training or model
selection. The job name is the idempotency token, so a redelivered event registers
nothing new.
"""

import hashlib
import io
import json
import os
import tarfile

import boto3

MODEL_PACKAGE_GROUP = os.environ["MODEL_PACKAGE_GROUP"]
TRAINING_ROLE_ARN = os.environ["TRAINING_ROLE_ARN"]
INFERENCE_IMAGE = os.environ["INFERENCE_IMAGE"]

s3 = boto3.client("s3")
sagemaker = boto3.client("sagemaker")


def pinned_artefact(desc: dict) -> tuple[dict, bytes]:
    bucket, key = desc["ModelArtifacts"]["S3ModelArtifacts"].removeprefix("s3://").split("/", 1)
    head = s3.head_object(Bucket=bucket, Key=key)
    if head["LastModified"] > desc["TrainingEndTime"]:
        raise ValueError(f"refused: s3://{bucket}/{key} changed after the training job ended")
    body = s3.get_object(Bucket=bucket, Key=key, VersionId=head["VersionId"])["Body"].read()
    return {"artefact_version_id": head["VersionId"], "artefact_sha256": hashlib.sha256(body).hexdigest()}, body


def metrics_of(body: bytes) -> dict:
    with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as tar:
        member = next((m for m in tar.getmembers() if m.name.removeprefix("./") == "metrics.json"), None)
        if member is None or not member.isfile():
            raise ValueError("artefact lacks metrics.json")
        return json.load(tar.extractfile(member))


def main(event, _context):
    job = event["detail"]["TrainingJobName"]
    desc = sagemaker.describe_training_job(TrainingJobName=job)
    # The rule matches the event; the job's current record is what counts.
    if desc["TrainingJobStatus"] != "Completed" or desc["RoleArn"] != TRAINING_ROLE_ARN:
        return {"skipped": job, "status": desc["TrainingJobStatus"], "role": desc["RoleArn"]}
    pinned, body = pinned_artefact(desc)
    metrics = metrics_of(body)
    package = sagemaker.create_model_package(
        ModelPackageGroupName=MODEL_PACKAGE_GROUP,
        ModelPackageDescription=f"tiny3d trained by {job} on snapshot {metrics['snapshot']}",
        ModelApprovalStatus="PendingManualApproval",
        InferenceSpecification={
            "Containers": [{"Image": INFERENCE_IMAGE, "ModelDataUrl": desc["ModelArtifacts"]["S3ModelArtifacts"]}],
            "SupportedContentTypes": ["video/mp4"], "SupportedResponseMIMETypes": ["application/json"],
        },
        CustomerMetadataProperties={
            "training_job": job, "snapshot": metrics["snapshot"],
            "test_accuracy": str(metrics["test_accuracy"]), "num_test": str(metrics["num_test"]),
            "selection_val_accuracy": str(metrics["selection_val_accuracy"]), **pinned,
        },
        ClientToken=job,
    )
    record = {"event": "registered", "model_package_arn": package["ModelPackageArn"], "training_job": job,
              "test_accuracy": metrics["test_accuracy"], **pinned}
    print(json.dumps(record))
    return record
