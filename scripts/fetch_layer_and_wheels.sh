#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Fetches the binary Python packages the stacks ship but the repository does not
# commit, each pinned by version and hash under scripts/requirements/:
#   infra/layers/opencv/python/  OpenCV and NumPy for the validation Lambda
#                                (Python 3.12, arm64), mounted at /opt/python
#   site/wheels/                 the gateway's wheels for Amazon Linux 2023
#                                (Python 3.12, arm64)
# Run with the repository's virtual environment (.venv) before `cdk synth`.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
pip=("$root/.venv/bin/python" -m pip --disable-pip-version-check)
platform=(--platform manylinux2014_aarch64 --platform manylinux_2_27_aarch64 --platform manylinux_2_28_aarch64
          --only-binary=:all: --implementation cp --require-hashes --no-deps)

layer="$root/infra/layers/opencv/python"
rm -rf "$layer" && mkdir -p "$layer"
"${pip[@]}" install --quiet --no-cache-dir --target "$layer" "${platform[@]}" --python-version 3.12 \
  -r "$root/scripts/requirements/validation-layer.txt"
# Lambda limits a function plus its layers to 250 MB unzipped.
find "$layer" -depth -type d \( -name tests -o -name __pycache__ \) -exec rm -rf {} +
find "$layer" -name '*.pyi' -delete
rm -rf "$layer/cv2/data" "$layer/bin" "$layer/numpy/f2py" "$layer/numpy/_core/include" "$layer/numpy/_pyinstaller"

wheels="$root/site/wheels"
rm -rf "$wheels" && mkdir -p "$wheels"
"${pip[@]}" download --quiet --no-cache-dir --dest "$wheels" "${platform[@]}" --python-version 3.12 \
  -r "$root/scripts/requirements/gateway.txt"

du -sh "$layer" "$wheels"
