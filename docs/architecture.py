# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""What the sample deploys and how a clip becomes a model on a site gateway.

    python docs/architecture.py docs/architecture

One cluster per CDK stack; the numbered edges follow a clip from upload to the
gateway. Needs the packages in `requirements-docs.in` (`diagrams`, MIT; `Pillow`,
MIT-CMU) and the Graphviz `dot` binary (EPL-1.0), installed from the operating
system's package manager; the PNG is quantized to 256 colours to stay small.
"""
import sys

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import EC2, Lambda
from diagrams.aws.management import SystemsManager
from diagrams.aws.ml import Sagemaker, SagemakerModel
from diagrams.aws.network import APIGateway, CloudFront, Endpoint
from diagrams.aws.security import KMS, Cognito, Guardduty
from diagrams.aws.storage import S3
from diagrams.onprem.client import User, Users
from PIL import Image

STEP = {"color": "#1f4e79", "penwidth": "2.0", "fontsize": "13"}
SIDE = {"color": "#6d6d6d", "style": "dashed", "fontsize": "12"}


def stack(label, fill, border):
    return Cluster(label, graph_attr={"bgcolor": fill, "pencolor": border, "penwidth": "2.0",
                                      "style": "rounded,filled", "fontsize": "16", "margin": "20"})


graph = {"fontsize": "20", "bgcolor": "white", "pad": "0.6", "ranksep": "0.9", "nodesep": "0.8", "splines": "spline",
         "labelloc": "t"}
out = sys.argv[1]
with Diagram("AnyCompany Robotics conveyor-video sample: from contributed clip to signed model at each site",
             filename=out, show=False, direction="LR", graph_attr=graph):
    staff = Users("Factory staff\n(contributors)")
    engineer = User("ML engineer")
    operator = User("Site operator")

    with stack("ConveyorIntake stack", "#fff4e5", "#e07b00"):
        cdn = CloudFront("CloudFront\nportal")
        idp = Cognito("Cognito\nsign-in")
        api = APIGateway("HTTP API")
        presign = Lambda("Presign function")
        status = Lambda("Upload status function\nown uploads only")
        intake = S3("Intake bucket")
        scan = Guardduty("GuardDuty Malware\nProtection for S3")
        validate = Lambda("Validation function\nprobe + re-encode")
        curated = S3("Curated bucket")

    with stack("ConveyorMl stack", "#e8f0fa", "#1f4e79"):
        train = Sagemaker("SageMaker AI\ntraining (Spot)")
        register = Lambda("Registration function\ntest accuracy, digest")
        registry = SagemakerModel("Model Registry")
        release = Lambda("Release function")
        key = KMS("KMS signing key")
        releases = S3("Release bucket")

    with stack("ConveyorSite-<site> stack (one per site)", "#e9f5ea", "#2e7d32"):
        s3_endpoint = Endpoint("S3 gateway\nendpoint")
        gateway = EC2("Edge gateway\nverify, install,\nclassify, local UI")

    bundle = S3("CDK assets bucket\nsite bundle")
    repos = S3("Amazon Linux 2023\npackage repositories\n(AWS-owned)")

    ssm = SystemsManager("Session Manager")

    staff >> Edge(label="sign in", **SIDE) >> idp
    staff >> Edge(label="1 portal", **STEP) >> cdn >> Edge(**STEP) >> api >> Edge(**STEP) >> presign
    staff >> Edge(label="2 upload clip\n(presigned PUT)", **STEP) >> intake
    api >> Edge(label="follow uploads\nGET /api/uploads", **SIDE) >> status
    intake >> Edge(label="tags", **SIDE) >> status
    scan >> Edge(label="3 scan", **STEP) >> intake
    intake >> Edge(label="4 clean clips", **STEP) >> validate >> Edge(**STEP) >> curated
    curated >> Edge(label="5 frozen snapshot", **STEP) >> train
    engineer >> Edge(label="start training,\nheld-out test clips", **SIDE) >> train
    train >> Edge(label="6 on completion", **STEP) >> register >> Edge(label="register", **STEP) >> registry
    engineer >> Edge(label="7 approve", **SIDE) >> registry
    registry >> Edge(label="8 on approval", **STEP) >> release
    release >> Edge(label="sign", **SIDE) >> key
    release >> Edge(label="9 signed release", **STEP) >> releases
    releases >> Edge(label="10 fetch every 15 min\n(no internet route)", **STEP) >> s3_endpoint >> Edge(**STEP) >> gateway
    bundle >> Edge(label="first boot:\nsite bundle", **SIDE) >> s3_endpoint
    repos >> Edge(label="first boot:\ndnf python3.12", **SIDE) >> s3_endpoint
    operator >> Edge(label="11 open the UI:\nport forwarding", **STEP) >> ssm
    ssm >> Edge(label="localhost:8080\n(no inbound port)", **STEP) >> gateway

png = f"{out}.png"
Image.open(png).convert("RGB").quantize(256).save(png, optimize=True)
