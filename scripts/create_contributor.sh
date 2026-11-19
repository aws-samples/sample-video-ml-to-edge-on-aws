#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Creates a portal contributor in one site group and prints a one-time password,
# which the contributor replaces at first sign-in.
# Usage: scripts/create_contributor.sh <username> <site>
set -euo pipefail
USERNAME=$1
SITE=$2
POOL=$(aws cloudformation describe-stacks --stack-name ConveyorIntake \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" --output text)
TEMP_PASSWORD="$(openssl rand -base64 18)Aa1!"
# The password goes in a private file, not on a command line, where ps would show it;
# printf is a bash builtin, so writing the file starts no process either. Base64 needs no JSON escaping.
umask 077
REQUEST=$(mktemp)
trap 'rm -f "$REQUEST"' EXIT
printf '{"UserPoolId": "%s", "Username": "%s", "TemporaryPassword": "%s", "MessageAction": "SUPPRESS"}\n' \
  "$POOL" "$USERNAME" "$TEMP_PASSWORD" >"$REQUEST"
aws cognito-idp admin-create-user --cli-input-json "file://$REQUEST" >/dev/null
aws cognito-idp admin-add-user-to-group --user-pool-id "$POOL" --username "$USERNAME" --group-name "$SITE"
echo "created $USERNAME in group $SITE; one-time password: $TEMP_PASSWORD"
