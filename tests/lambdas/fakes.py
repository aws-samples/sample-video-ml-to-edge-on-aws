# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""In-memory stand-ins for the boto3 clients the Lambdas call."""

from __future__ import annotations

from pathlib import Path


class FakeS3:
    def __init__(self, objects: dict | None = None):
        self.objects = dict(objects or {})
        self.puts = {}
        self.order = []
        self.downloads = []

    def download_file(self, bucket, key, path, ExtraArgs=None):
        self.downloads.append((bucket, key, ExtraArgs))
        Path(path).write_bytes(self.objects[(bucket, key)])

    def upload_file(self, path, bucket, key):
        self.puts[(bucket, key)] = {"Body": Path(path).read_bytes()}

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.order.append(Key)
        self.puts[(Bucket, Key)] = {"Body": Body if isinstance(Body, bytes) else Body.read(), **kwargs}
