# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Publication gate: exits 1 unless scripts/fetch_dataset.py pins a real SHA-256
for the dataset archive. Normal CI does not run it, because the archive is
published with the public repository.

    python scripts/ci/dataset_published.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fetch_dataset  # noqa: E402


def main() -> int:
    if re.fullmatch(r"[0-9a-f]{64}", fetch_dataset.DATASET_SHA256):
        print(f"dataset archive pinned: {fetch_dataset.DATASET_SHA256}")
        return 0
    print(f"scripts/fetch_dataset.py: DATASET_SHA256 is {fetch_dataset.DATASET_SHA256!r}, not the SHA-256 of the published dataset-v1 archive")
    return 1


if __name__ == "__main__":
    sys.exit(main())
