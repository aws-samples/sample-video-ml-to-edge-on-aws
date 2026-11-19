# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""A local P-256 key that signs the way the KMS release key does: ECDSA_SHA_256
over a RAW message, returning a DER signature."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def openssl(*args, data: bytes | None = None) -> bytes:
    return subprocess.run(["openssl", *args], input=data, check=True, capture_output=True).stdout


class LocalSigningKey:
    def __init__(self, directory: Path):
        self.private = directory / "release-key.pem"
        self.public = directory / "release-public-key.pem"
        openssl("genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-out", str(self.private))
        openssl("pkey", "-in", str(self.private), "-pubout", "-out", str(self.public))

    def sign(self, message: bytes) -> bytes:
        with tempfile.NamedTemporaryFile() as fh:
            fh.write(message)
            fh.flush()
            return openssl("dgst", "-sha256", "-sign", str(self.private), fh.name)


class FakeKms:
    """kms.sign backed by a LocalSigningKey; accepts only what the release Lambda sends."""

    def __init__(self, key: LocalSigningKey):
        self.key = key
        self.calls = []

    def sign(self, KeyId, Message, MessageType, SigningAlgorithm):
        assert (MessageType, SigningAlgorithm) == ("RAW", "ECDSA_SHA_256")
        self.calls.append(KeyId)
        return {"Signature": self.key.sign(Message), "KeyId": KeyId}
