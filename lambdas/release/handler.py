# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Publishes an approved model package as a signed release for every site.

Invoked by the EventBridge rule for "SageMaker Model Package State Change" events
with ModelApprovalStatus Approved in the sample's model package group. Copies the
object version of model.tar.gz recorded at registration (and refuses it unless its
SHA-256 still matches the registered digest, since the training role can write
training output) to releases/<version>/model.tar.gz in the release bucket,
writes releases/<version>/release.json (version, SHA-256 of the artefact) and its
KMS ECDSA P-256 signature release.json.sig, then points channels/<site>.json at
the version. Gateways verify the signature over release.json and the artefact's
digest against it before installing.
"""

import hashlib
import json
import os
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import boto3

RELEASE_BUCKET = os.environ["RELEASE_BUCKET"]
SIGNING_KEY_ID = os.environ["SIGNING_KEY_ID"]
SITES = os.environ["SITES"].split(",")
REQUIRED = {"model.onnx", "labels.json", "preprocess.py", "metrics.json"}

s3 = boto3.client("s3")
kms = boto3.client("kms")
sagemaker = boto3.client("sagemaker")


def split_s3_uri(uri: str) -> tuple[str, str]:
    bucket, _, key = uri.removeprefix("s3://").partition("/")
    return bucket, key


def check_artefact(path: Path) -> None:
    """Refuses a tarball missing a release file or holding a member that would
    extract outside its directory."""
    with tarfile.open(path, "r:gz") as tar:
        names = set()
        for member in tar.getmembers():
            name = member.name.removeprefix("./")
            if name.startswith("/") or ".." in Path(name).parts or not (member.isfile() or member.isdir()):
                raise ValueError(f"unsafe member in artefact: {member.name}")
            names.add(name)
    missing = REQUIRED - names
    if missing:
        raise ValueError(f"artefact lacks {sorted(missing)}")


def sha256_hex(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publish(package: dict) -> dict:
    version = f"v{package['ModelPackageVersion']}"
    bucket, key = split_s3_uri(package["InferenceSpecification"]["Containers"][0]["ModelDataUrl"])
    registered = package["CustomerMetadataProperties"]
    with tempfile.TemporaryDirectory() as tmp:
        artefact = Path(tmp) / "model.tar.gz"
        s3.download_file(bucket, key, str(artefact), ExtraArgs={"VersionId": registered["artefact_version_id"]})
        digest = sha256_hex(artefact)
        if digest != registered["artefact_sha256"]:
            raise ValueError(f"artefact digest {digest} differs from the registered {registered['artefact_sha256']}")
        check_artefact(artefact)
        release = {
            "version": version,
            "artefact": f"releases/{version}/model.tar.gz",
            "sha256": digest,
            "model_package_arn": package["ModelPackageArn"],
            "released_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        s3.upload_file(str(artefact), RELEASE_BUCKET, release["artefact"])
    body = (json.dumps(release, indent=1, sort_keys=True) + "\n").encode()
    signature = kms.sign(KeyId=SIGNING_KEY_ID, Message=body, MessageType="RAW",
                         SigningAlgorithm="ECDSA_SHA_256")["Signature"]
    s3.put_object(Bucket=RELEASE_BUCKET, Key=f"releases/{version}/release.json", Body=body,
                  ContentType="application/json")
    s3.put_object(Bucket=RELEASE_BUCKET, Key=f"releases/{version}/release.json.sig", Body=signature,
                  ContentType="application/octet-stream")
    for site in SITES:
        s3.put_object(Bucket=RELEASE_BUCKET, Key=f"channels/{site}.json",
                      Body=json.dumps({"version": version}).encode(), ContentType="application/json")
    print(json.dumps({"event": "released", **release, "sites": SITES}))
    return release


def main(event, _context):
    arn = event["detail"]["ModelPackageArn"]
    package = sagemaker.describe_model_package(ModelPackageName=arn)
    # The rule matches the event; the package's current status is what counts.
    if package["ModelApprovalStatus"] != "Approved":
        return {"skipped": arn, "status": package["ModelApprovalStatus"]}
    return publish(package)
