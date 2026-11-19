# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Runs scripts/create_contributor.sh against a fake `aws` on PATH."""

import json
import os
import subprocess

from conftest import ROOT

# Logs every call; keeps a copy of the --cli-input-json file and its mode.
FAKE_AWS = """#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "$LOG/argv"
case "$1 $2" in
  "cloudformation describe-stacks") echo eu-west-1_pool ;;
  "cognito-idp admin-create-user")
    file=${4#file://}
    stat -c %a "$file" > "$LOG/mode"
    cp "$file" "$LOG/request.json"
    echo "$file" > "$LOG/path" ;;
esac
"""


def test_the_password_reaches_cognito_in_a_private_file_and_never_on_a_command_line(tmp_path):
    fakebin, log = tmp_path / "fakebin", tmp_path / "log"
    fakebin.mkdir()
    log.mkdir()
    (fakebin / "aws").write_text(FAKE_AWS)
    (fakebin / "aws").chmod(0o755)
    env = {**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}", "LOG": str(log)}
    result = subprocess.run(["bash", str(ROOT / "scripts" / "create_contributor.sh"), "operator-1", "factory-a"],
                            env=env, capture_output=True, text=True, check=True)
    request = json.loads((log / "request.json").read_text())
    password = request["TemporaryPassword"]
    assert request | {"TemporaryPassword": None} == {"UserPoolId": "eu-west-1_pool", "Username": "operator-1",
                                                     "TemporaryPassword": None, "MessageAction": "SUPPRESS"}
    assert password not in (log / "argv").read_text()
    assert (log / "mode").read_text().strip() == "600"
    assert not os.path.exists((log / "path").read_text().strip())
    assert result.stdout.count(password) == 1
