#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Removes the sample from the current account and Region, then lists what stays.
# CloudFormation cannot delete a model package group that still holds model
# packages, so those are deleted first; the buckets empty themselves on delete,
# and the log groups Lambda created at run time are deleted after the stacks.
# Usage: scripts/teardown.sh <region>
set -euo pipefail
REGION=$1
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GROUP=conveyor-events

for arn in $(aws sagemaker list-model-packages --region "$REGION" --model-package-group-name "$GROUP" \
    --query 'ModelPackageSummaryList[].ModelPackageArn' --output text 2>/dev/null); do
  aws sagemaker delete-model-package --region "$REGION" --model-package-name "$arn"
  echo "deleted $arn"
done
(cd "$ROOT/infra" && npx cdk destroy --all --force)
# CDK's own provider functions (bucket auto-delete, default security group
# restriction) log to groups Lambda creates at run time, outside the stacks.
for group in $(aws logs describe-log-groups --region "$REGION" --log-group-name-prefix /aws/lambda/Conveyor \
    --query 'logGroups[].logGroupName' --output text); do
  aws logs delete-log-group --region "$REGION" --log-group-name "$group"
  echo "deleted log group $group"
done

cat <<EOF2

Left in place:
- KMS keys of the stacks, pending deletion for 30 days:
$(aws kms list-keys --region "$REGION" --query 'Keys[].KeyId' --output text | tr '\t' '\n' | while read -r key; do
  aws kms describe-key --region "$REGION" --key-id "$key" --query "KeyMetadata.[KeyState,Description]" --output text
done | grep PendingDeletion | sed 's/^/    /' || true)
- SageMaker training logs in /aws/sagemaker/TrainingJobs, streams tiny3d-*
- training jobs (SageMaker keeps their records; they cost nothing)
- the CDK bootstrap stack CDKToolkit and its asset bucket
- IAM policies ConveyorSampleCfnExec, ConveyorSampleCfnExecCompute and ConveyorSampleBoundary (scripts/bootstrap.sh)
EOF2
