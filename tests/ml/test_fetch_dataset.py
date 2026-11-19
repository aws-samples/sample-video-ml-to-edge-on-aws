# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import hashlib
import io
import json
import tarfile

import pytest

from conftest import ROOT, import_from

fetch_dataset = import_from(ROOT / "scripts", "fetch_dataset")


def archive(tmp_path, members, manifest_files):
    path = tmp_path / "dataset.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        for name, data in {**members, "manifest.json": json.dumps({"files": manifest_files}).encode()}.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


@pytest.fixture(autouse=True)
def served(monkeypatch):
    """Answers an https URL with the archive file its path names."""
    monkeypatch.setattr(fetch_dataset.urllib.request, "urlopen",
                        lambda url, timeout: open(fetch_dataset.urllib.parse.urlsplit(url).path, "rb"))


def https(path):
    return f"https://example.test{path}"


def entry(name, data):
    return {"path": name, "sha256": hashlib.sha256(data).hexdigest()}


def pinned(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_archive_matching_its_manifest_verifies(tmp_path):
    clip = b"clip-bytes"
    path = archive(tmp_path, {"factory-a/test/jam/jam-000.mp4": clip}, [entry("factory-a/test/jam/jam-000.mp4", clip)])
    dest = tmp_path / "out"
    assert fetch_dataset.fetch(https(path), pinned(path), dest) == []
    assert (dest / "factory-a/test/jam/jam-000.mp4").read_bytes() == clip


def test_altered_or_missing_clip_is_reported(tmp_path):
    path = archive(tmp_path, {"a/x.mp4": b"changed"}, [entry("a/x.mp4", b"original"), entry("a/y.mp4", b"y")])
    assert fetch_dataset.fetch(https(path), pinned(path), tmp_path / "out") == ["digest mismatch a/x.mp4", "missing a/y.mp4"]


def test_an_archive_other_than_the_pinned_one_is_refused_before_extraction(tmp_path):
    clip = b"clip-bytes"
    path = archive(tmp_path, {"a/x.mp4": clip}, [entry("a/x.mp4", clip)])
    with pytest.raises(SystemExit, match="refusing the archive"):
        fetch_dataset.fetch(https(path), hashlib.sha256(b"another archive").hexdigest(), tmp_path / "out")
    assert not (tmp_path / "out" / "a/x.mp4").exists()


def test_member_escaping_the_destination_is_refused(tmp_path):
    path = archive(tmp_path, {"../escape.mp4": b"x"}, [])
    try:
        fetch_dataset.fetch(https(path), pinned(path), tmp_path / "out")
    except tarfile.TarError:
        pass
    assert not (tmp_path / "escape.mp4").exists()


def test_a_url_that_is_not_https_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="not https"):
        fetch_dataset.fetch(archive(tmp_path, {}, []).as_uri(), "", tmp_path / "out")
