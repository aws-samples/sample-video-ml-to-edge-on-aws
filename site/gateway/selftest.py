# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Scores an installed release on the held-out clips it ships under selftest/<label>/.

    python selftest.py <model-dir>

Prints {version, accuracy, correct, total, per_label, mean_latency_ms}. Exits 1
when the release has no self-test clips or scores below MIN_ACCURACY, so the
gateway refuses it and keeps the running model.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from classifier import Classifier

# A release that misses more than one held-out clip in ten is refused.
MIN_ACCURACY = 0.9


def run(model_dir: Path) -> dict:
    classifier = Classifier(model_dir)
    clips = sorted((model_dir / "selftest").glob("*/*.mp4"))
    if not clips:
        raise SystemExit(f"no self-test clips under {model_dir / 'selftest'}")
    hits, totals, latencies = defaultdict(int), defaultdict(int), []
    for clip in clips:
        truth = clip.parent.name
        result = classifier.predict(str(clip))
        totals[truth] += 1
        hits[truth] += result["label"] == truth
        latencies.append(result["latency_ms"])
    release = json.loads((model_dir / "release.json").read_text())
    return {
        "version": release["version"],
        "accuracy": round(sum(hits.values()) / len(clips), 4),
        "correct": sum(hits.values()),
        "total": len(clips),
        "per_label": {label: f"{hits[label]}/{totals[label]}" for label in sorted(totals)},
        "mean_latency_ms": round(sum(latencies) / len(latencies), 1),
    }


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    result = run(Path(sys.argv[1]))
    print(json.dumps(result))
    if result["accuracy"] < MIN_ACCURACY:
        print(f"scored {result['correct']}/{result['total']}, below the {MIN_ACCURACY:.0%} minimum", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
