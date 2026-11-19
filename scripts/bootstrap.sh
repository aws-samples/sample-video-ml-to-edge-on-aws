#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Bootstraps the current account and Region with a least-privilege CloudFormation
# execution role instead of the default AdministratorAccess:
#   - infra/cfn-exec-policy.json and infra/cfn-exec-policy-compute.json (two
#     policies, as one exceeds the managed policy size limit) limit deployments to
#     the actions the stacks' resource types need, on the sample's resources, and
#     let them create IAM roles only named Conveyor* and only with the
#     ConveyorSampleBoundary permissions boundary;
#   - infra/permissions-boundary.json is that boundary: every role the app creates
#     carries it (infra/cdk.json), so no deployed role can reach beyond the
#     services the sample uses or change IAM.
# It creates IAM policies and roles, so an administrator runs it, once per account
# and Region and again whenever one of those three files changes; operators with
# infra/operator-policy.json cannot.
# Usage: scripts/bootstrap.sh <region>
set -euo pipefail
REGION=$1
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text --region "$REGION")

# IAM refuses a policy variable in the account field of an ARN, so the files' ${aws:PrincipalAccount}
# becomes this account's id.
upsert_policy() {
  local name=$1 arn="arn:aws:iam::$ACCOUNT:policy/$1" doc
  doc=$(sed "s/\${aws:PrincipalAccount}/$ACCOUNT/g" "$2")
  if aws iam get-policy --policy-arn "$arn" >/dev/null 2>&1; then
    # A managed policy keeps at most five versions; drop the oldest non-default one.
    if [ "$(aws iam list-policy-versions --policy-arn "$arn" --query 'length(Versions)')" -ge 5 ]; then
      aws iam delete-policy-version --policy-arn "$arn" --version-id \
        "$(aws iam list-policy-versions --policy-arn "$arn" --query 'Versions[?!IsDefaultVersion].VersionId | [-1]' --output text)"
    fi
    aws iam create-policy-version --policy-arn "$arn" --policy-document "$doc" --set-as-default >/dev/null
  else
    aws iam create-policy --policy-name "$name" --policy-document "$doc" \
      --tags Key=project,Value=sample-video-ml-to-edge >/dev/null
  fi
  echo "$arn"
}

upsert_policy ConveyorSampleBoundary "$ROOT/infra/permissions-boundary.json"
EXEC=$(upsert_policy ConveyorSampleCfnExec "$ROOT/infra/cfn-exec-policy.json")
COMPUTE=$(upsert_policy ConveyorSampleCfnExecCompute "$ROOT/infra/cfn-exec-policy-compute.json")
# An existing toolkit also serves every other CDK app in this account and Region, which
# then deploys with the sample's execution policies; say what they were.
PREVIOUS=$(aws cloudformation describe-stacks --stack-name CDKToolkit --region "$REGION" --output json \
  --query "Stacks[0].Parameters[?ParameterKey=='CloudFormationExecutionPolicies'].ParameterValue | [0]" 2>/dev/null) || PREVIOUS=
if [ -n "$PREVIOUS" ] && [ "$PREVIOUS" != "\"$EXEC,$COMPUTE\"" ]; then
  PREVIOUS=${PREVIOUS//\"/}
  PREVIOUS=${PREVIOUS:-arn:aws:iam::aws:policy/AdministratorAccess}
  echo "warning: replacing the execution policies of the existing CDKToolkit in $REGION ($PREVIOUS);" \
    "restore them with: (cd infra && npx cdk bootstrap --cloudformation-execution-policies $PREVIOUS)" >&2
fi
cd "$ROOT/infra"
npx cdk bootstrap "aws://$ACCOUNT/$REGION" --cloudformation-execution-policies "$EXEC,$COMPUTE"
