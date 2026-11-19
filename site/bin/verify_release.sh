#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Verifies a downloaded release before it is installed:
#   1. release.json.sig is a valid ECDSA P-256 / SHA-256 signature over the exact
#      bytes of release.json under the pinned release public key;
#   2. release.json names the expected version;
#   3. the artefact's SHA-256 equals the digest release.json records.
# Usage: verify_release.sh <release.json> <release.json.sig> <public-key.pem> <artefact> <version>
set -euo pipefail

RELEASE=$1
SIGNATURE=$2
PUBLIC_KEY=$3
ARTEFACT=$4
VERSION=$5

if ! openssl dgst -sha256 -verify "$PUBLIC_KEY" -signature "$SIGNATURE" "$RELEASE" >/dev/null 2>&1; then
  echo "signature verification failed for $RELEASE" >&2
  exit 1
fi
read -r NAMED EXPECTED < <(python3.12 -c 'import json, sys; r = json.load(open(sys.argv[1])); print(r["version"], r["sha256"])' "$RELEASE")
if [[ "$NAMED" != "$VERSION" ]]; then
  echo "release.json names version $NAMED, expected $VERSION" >&2
  exit 1
fi
ACTUAL=$(openssl dgst -sha256 -r "$ARTEFACT" | cut -d' ' -f1)
if [[ "$ACTUAL" != "$EXPECTED" ]]; then
  echo "sha256 mismatch: release.json says $EXPECTED, artefact is $ACTUAL" >&2
  exit 1
fi
echo "release $VERSION verified"
