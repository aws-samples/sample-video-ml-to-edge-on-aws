# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""The training job installs ml/train/requirements.txt; CI tests requirements-train.txt."""

import re

import pytest

from conftest import ROOT


def pins(path):
    """{name: (version, has_hash)} for every requirement in a pip-compiled file."""
    found = {}
    for block in re.split(r"\n(?=[A-Za-z])", path.read_text()):
        match = re.match(r"([A-Za-z0-9_.-]+)==([^\s;\\]+)", block)
        if match:
            found[match[1].lower()] = (match[2], "--hash=sha256:" in block)
    return found


JOB = pins(ROOT / "ml" / "train" / "requirements.txt")


def test_every_package_the_job_installs_is_pinned_with_a_hash():
    assert JOB and all(has_hash for _, has_hash in JOB.values())


def test_the_job_keeps_the_image_torch():
    assert "torch" not in JOB


@pytest.mark.parametrize("lock", ["requirements-train.txt", "requirements-dev.txt"])
@pytest.mark.parametrize("package", ["opencv-python-headless", "onnx", "onnxruntime"])
def test_ci_tests_the_versions_the_job_installs(lock, package):
    assert pins(ROOT / lock)[package][0] == JOB[package][0]
