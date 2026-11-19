# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Runs checkov over synthesized CloudFormation templates and fails on any finding
not listed in scripts/ci/checkov-baseline.json, or on a baseline entry that no
longer matches a finding, so the baseline stays a current list of accepted risks.

    python scripts/ci/checkov_gate.py infra/cdk.out

Each baseline entry is {"check", "resource", "reason"}; resource is
"<template file>:<CloudFormation type>.<logical id>". Before the real scan the gate
checks that it rejects an unhardened canary bucket.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

BASELINE = Path(__file__).resolve().parent / "checkov-baseline.json"


def findings(directory: Path) -> set[tuple[str, str]]:
    run = subprocess.run(["checkov", "-d", str(directory), "--framework", "cloudformation",
                          "-o", "json", "--quiet", "--compact"], capture_output=True, text=True)
    if run.returncode not in (0, 1):
        sys.exit(f"checkov failed to run: {run.stderr[-2000:]}")
    reports = json.loads(run.stdout or "[]")
    reports = reports if isinstance(reports, list) else [reports]
    found = set()
    for report in reports:
        for check in report.get("results", {}).get("failed_checks", []):
            name = Path(check["file_path"]).name
            found.add((check["check_id"], f"{name}:{check['resource']}"))
    return found


def canary_rejected() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "Canary.template.json").write_text(
            json.dumps({"Resources": {"Canary": {"Type": "AWS::S3::Bucket", "Properties": {}}}}))
        return bool(findings(Path(tmp)))


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    if not canary_rejected():
        sys.exit("FATAL: checkov passed an unhardened canary bucket; the gate does not gate")
    print("canary rejected: gate fires")
    entries = json.loads(BASELINE.read_text())
    missing_reason = [e for e in entries if not e.get("reason", "").strip()]
    if missing_reason:
        sys.exit(f"FATAL: baseline entries without a reason: {missing_reason}")
    accepted = {(e["check"], e["resource"]) for e in entries}
    found = findings(Path(sys.argv[1]))
    new = sorted(found - accepted)
    stale = sorted(accepted - found)
    for check, resource in new:
        print(f"NEW      {check} {resource}")
    for check, resource in stale:
        print(f"STALE    {check} {resource} (remove it from the baseline)")
    print(f"checkov gate: {len(found)} finding(s), {len(new)} new, {len(stale)} stale baseline entries")
    return 1 if new or stale else 0


if __name__ == "__main__":
    sys.exit(main())
