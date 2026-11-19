#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Installs the gateway on first boot (run from EC2 user data).
# Usage: install.sh <site-bundle-dir> <site> <release-bucket> <signing-key-arn> <region>
#
# The subnet has no internet route, so Python packages come as wheels inside the
# site bundle and are unpacked, not pip-installed. The release public key is read
# once from KMS and pinned on disk; every later release is verified against it.
set -euo pipefail

SRC=$1 SITE=$2 BUCKET=$3 KEY_ARN=$4 REGION=$5
BASE=/opt/conveyor

id conveyor >/dev/null 2>&1 || useradd --system --no-create-home --shell /sbin/nologin conveyor
mkdir -p "$BASE/lib" "$BASE/state"
cp -r "$SRC/bin" "$SRC/gateway" "$BASE/"
for wheel in "$SRC"/wheels/*.whl; do
  python3.12 -m zipfile -e "$wheel" "$BASE/lib"
done
printf 'SITE=%s\nRELEASE_BUCKET=%s\nREGION=%s\n' "$SITE" "$BUCKET" "$REGION" > "$BASE/env"

aws kms get-public-key --key-id "$KEY_ARN" --region "$REGION" --query PublicKey --output text \
  | base64 -d > "$BASE/release-public-key.der"
openssl pkey -pubin -inform DER -in "$BASE/release-public-key.der" -out "$BASE/release-public-key.pem"
rm "$BASE/release-public-key.der"

chown -R root:root "$BASE"
chmod 0755 "$BASE" "$BASE/state"
cp "$SRC"/systemd/conveyor-* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now conveyor-ui.service conveyor-fetch.timer
systemctl start conveyor-fetch.service || echo "first fetch failed; the timer retries"
