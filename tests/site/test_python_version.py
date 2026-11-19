# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""The gateway runs the python3.12 package of Amazon Linux 2023 with the package
versions the CI tests run, so a test pass covers what the gateway executes."""

import re

from conftest import ROOT

SITE = ROOT / "site"
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)", re.MULTILINE)


def pins(path):
    return {name.lower(): version for name, version in PIN.findall(path.read_text())}


def test_gateway_scripts_and_units_call_python312_only():
    files = [SITE / "install.sh", *(SITE / "bin").iterdir(), *(SITE / "systemd").iterdir()]
    calls = [(f.name, m) for f in files for m in re.findall(r"\bpython3[.\d]*", f.read_text())]
    assert calls, "the gateway scripts call no Python"
    assert {m for _, m in calls} == {"python3.12"}, calls
    assert "/usr/bin/python3.12 " in (SITE / "systemd" / "conveyor-ui.service").read_text()


def test_gateway_wheels_are_cp312():
    script = (ROOT / "scripts" / "fetch_layer_and_wheels.sh").read_text()
    assert re.findall(r"--python-version (\S+)", script) == ["3.12", "3.12"]


def test_gateway_pins_match_the_ci_lock():
    gateway = pins(ROOT / "scripts" / "requirements" / "gateway.txt")
    dev = pins(ROOT / "requirements-dev.txt")
    assert {"numpy", "onnxruntime", "opencv-python-headless"} <= gateway.keys()
    assert {name: dev.get(name) for name in gateway} == gateway
