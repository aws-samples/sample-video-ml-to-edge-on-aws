# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import json
import sys

import pytest

from conftest import ROOT, import_from

selftest = import_from(ROOT / "site" / "gateway", "selftest")


def score(correct, total=16):
    return {"version": "v6", "accuracy": round(correct / total, 4), "correct": correct, "total": total,
            "per_label": {}, "mean_latency_ms": 80.0}


@pytest.mark.parametrize("correct, code", [(16, 0), (15, 0), (14, 1), (0, 1)])
def test_main_refuses_a_release_below_the_minimum(monkeypatch, capsys, correct, code):
    monkeypatch.setattr(selftest, "run", lambda model_dir: score(correct))
    monkeypatch.setattr(sys, "argv", ["selftest.py", "/opt/conveyor/model-v6"])
    assert selftest.main() == code
    out, err = capsys.readouterr()
    assert json.loads(out)["correct"] == correct
    assert ("below the 90% minimum" in err) == bool(code)
