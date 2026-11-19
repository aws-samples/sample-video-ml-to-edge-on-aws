# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Reads the deployed stacks' CloudFormation outputs, which name every bucket,
role and pool the operator scripts use."""

import boto3


def outputs(session: boto3.Session, stack: str) -> dict[str, str]:
    desc = session.client("cloudformation").describe_stacks(StackName=stack)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in desc.get("Outputs", [])}
