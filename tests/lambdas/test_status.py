# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import io
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest
from botocore.exceptions import ClientError

from conftest import ROOT, import_from

ENV = {"INTAKE_BUCKET": "intake", "CURATED_BUCKET": "curated", "SITES": "factory-a,factory-b",
       "LABELS": "normal,jam,drop,empty"}
A, B, C, D, E, F = ("a" * 32, "b" * 32, "c" * 32, "d" * 32, "e" * 32, "f" * 32)
T0 = datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc)
MINE = {"contributor": "me"}
CLEAN = {**MINE, "GuardDutyMalwareScanStatus": "NO_THREATS_FOUND"}


def error(code):
    return ClientError({"Error": {"Code": code}}, "op")


class FakeS3:
    """Intake objects as {key: tags}, uploaded a minute apart in insertion order;
    curated and rejected objects as {key: body}. Listings return `page` keys at a time."""

    def __init__(self, intake, curated, page=1000):
        self.intake, self.curated, self.page, self.calls = intake, curated, page, []
        self.uploaded = {key: T0 + timedelta(minutes=n) for n, key in enumerate(intake)}
        self.failing = set()

    def list_objects_v2(self, Bucket, Prefix, MaxKeys=None, ContinuationToken="0"):
        self.calls.append(("list", Bucket, Prefix))
        if Prefix in self.failing:
            raise error("SlowDown")
        source = self.intake if Bucket == "intake" else self.curated
        keys = sorted(k for k in source if k.startswith(Prefix))
        start, size = int(ContinuationToken), min(MaxKeys or self.page, self.page)
        page = {"Contents": [{"Key": k, "LastModified": self.uploaded.get(k, T0)} for k in keys[start:start + size]],
                "IsTruncated": start + size < len(keys)}
        if page["IsTruncated"]:
            page["NextContinuationToken"] = str(start + size)
        return page

    def get_object_tagging(self, Bucket, Key):
        self.calls.append(("tags", Bucket, Key))
        if Bucket != "intake" or Key not in self.intake:
            raise error("NoSuchKey")
        return {"TagSet": [{"Key": k, "Value": v} for k, v in self.intake[Key].items()]}

    def get_object(self, Bucket, Key):
        self.calls.append(("get", Bucket, Key))
        if Bucket != "curated" or Key not in self.curated:
            raise error("NoSuchKey")
        return {"Body": io.BytesIO(self.curated[Key])}


@pytest.fixture
def module():
    return import_from(ROOT / "lambdas" / "status", "handler", ENV)


def install(module, monkeypatch, intake, curated=None, page=1000):
    fake = FakeS3(intake, curated or {}, page)
    monkeypatch.setattr(module, "s3", fake)
    return fake


def ask(module, sub="me", groups="[factory-a]"):
    event = {"requestContext": {"authorizer": {"jwt": {"claims": {"sub": sub, "cognito:groups": groups}}}}}
    response = module.main(event, None)
    return response["statusCode"], json.loads(response["body"])


def test_every_state_is_reported_newest_first_with_the_upload_date(module, monkeypatch):
    install(module, monkeypatch, intake={
        f"intake/factory-a/jam/{A}.mp4": MINE,
        f"intake/factory-a/jam/{B}.mp4": CLEAN,
        f"intake/factory-a/jam/{C}.mp4": CLEAN,
        f"intake/factory-a/drop/{D}.mp4": CLEAN,
        f"intake/factory-a/empty/{E}.mp4": {**MINE, "GuardDutyMalwareScanStatus": "THREATS_FOUND"},
    }, curated={
        f"curated/factory-a/jam/{C}.mp4": b"clip",
        f"rejected/factory-a/drop/{D}.json": json.dumps({"reason": "codec-not-allowed"}).encode(),
    })
    code, body = ask(module)
    assert code == 200 and body["site"] == "factory-a"
    assert body["uploads"] == [
        {"clip": E, "label": "empty", "uploaded": "2026-10-13T09:04:00+00:00", "state": "rejected", "step": "scan",
         "reason": "malware found"},
        {"clip": D, "label": "drop", "uploaded": "2026-10-13T09:03:00+00:00", "state": "rejected", "step": "validate",
         "reason": "not a supported video"},
        {"clip": C, "label": "jam", "uploaded": "2026-10-13T09:02:00+00:00", "state": "accepted"},
        {"clip": B, "label": "jam", "uploaded": "2026-10-13T09:01:00+00:00", "state": "validating"},
        {"clip": A, "label": "jam", "uploaded": "2026-10-13T09:00:00+00:00", "state": "scanning"},
    ]


def test_another_contributors_clips_never_appear_and_are_not_read(module, monkeypatch):
    fake = install(module, monkeypatch, intake={
        f"intake/factory-a/jam/{A}.mp4": MINE,
        f"intake/factory-a/jam/{F}.mp4": {"contributor": "someone-else", "GuardDutyMalwareScanStatus": "NO_THREATS_FOUND"},
        f"intake/factory-a/jam/{E}.mp4": {"GuardDutyMalwareScanStatus": "NO_THREATS_FOUND"},
    }, curated={f"curated/factory-a/jam/{F}.mp4": b"clip"})
    assert [u["clip"] for u in ask(module)[1]["uploads"]] == [A]
    # Beyond the owner tag, nothing about the other clips is looked up.
    assert not any(F in key or E in key for op, _, key in fake.calls if op != "tags")
    assert ask(module, sub="someone-else")[1]["uploads"][0]["clip"] == F


def test_the_site_comes_from_the_callers_group(module, monkeypatch):
    fake = install(module, monkeypatch, intake={f"intake/factory-a/jam/{A}.mp4": MINE})
    assert ask(module, groups="[factory-b]")[1] == {"site": "factory-b", "uploads": []}
    assert all("factory-b" in key for _, _, key in fake.calls)


@pytest.mark.parametrize("groups", ["[]", "[factory-a factory-b]"])
def test_caller_needs_exactly_one_site_group(module, monkeypatch, groups):
    install(module, monkeypatch, intake={})
    assert ask(module, groups=groups)[0] == 403


def test_every_listing_page_is_read_so_the_newest_clip_on_a_later_page_comes_first(module, monkeypatch):
    # Keys list in name order, uploads come in time order: F is newest and lists last.
    intake = {f"intake/factory-a/jam/{c}.mp4": MINE for c in (A, B, C, D, E, F)}
    fake = install(module, monkeypatch, intake=intake, page=2)
    assert [u["clip"] for u in ask(module)[1]["uploads"]] == [F, E, D, C, B, A]
    assert len([c for c in fake.calls if c[:2] == ("list", "intake")]) == 3


def test_at_most_twenty_uploads_and_bounded_s3_calls(module, monkeypatch):
    clips = [f"{n:032x}" for n in range(150)]
    intake = {f"intake/factory-a/jam/{c}.mp4": {"contributor": "other"} for c in clips[:140]}
    intake.update({f"intake/factory-a/jam/{c}.mp4": MINE for c in clips[140:]})
    fake = install(module, monkeypatch, intake=intake, page=10)
    monkeypatch.setattr(module, "MAX_LISTED", 120)
    # Only the 120 listed keys are candidates; the 100 newest of them are other's.
    assert ask(module)[1]["uploads"] == []
    assert len([c for c in fake.calls if c[0] == "tags"]) == module.MAX_TAGGED
    assert len([c for c in fake.calls if c[:2] == ("list", "intake")]) == 12

    mine = {f"intake/factory-a/jam/{c}.mp4": MINE for c in clips}
    install(module, monkeypatch, intake=mine)
    uploads = ask(module)[1]["uploads"]
    assert len(uploads) == 20 and uploads[0]["clip"] == clips[119]  # the newest of the first 120 listed


def test_malformed_keys_are_skipped(module, monkeypatch):
    install(module, monkeypatch, intake={
        "intake/factory-a/jam/notes.txt": MINE,
        f"intake/factory-a/fire/{A}.mp4": MINE,
        f"intake/factory-a/jam/{B}.mp4": MINE,
    })
    assert [u["clip"] for u in ask(module)[1]["uploads"]] == [B]


def test_an_s3_error_on_one_verdict_marks_that_clip_unknown(module, monkeypatch):
    fake = install(module, monkeypatch, intake={
        f"intake/factory-a/jam/{A}.mp4": CLEAN,
        f"intake/factory-a/jam/{B}.mp4": CLEAN,
    }, curated={f"curated/factory-a/jam/{A}.mp4": b"clip"})
    fake.failing.add(f"curated/factory-a/jam/{B}.mp4")
    code, body = ask(module)
    assert code == 200
    assert [(u["clip"], u["state"]) for u in body["uploads"]] == [(B, "unknown"), (A, "accepted")]


def test_an_s3_error_on_an_owner_tag_skips_that_clip(module, monkeypatch):
    fake = install(module, monkeypatch, intake={f"intake/factory-a/jam/{A}.mp4": MINE, f"intake/factory-a/jam/{B}.mp4": MINE})
    tags = fake.get_object_tagging

    def flaky(Bucket, Key):
        if B in Key:
            raise error("InternalError")
        return tags(Bucket, Key)

    fake.get_object_tagging = flaky
    code, body = ask(module)
    assert code == 200 and [u["clip"] for u in body["uploads"]] == [A]


def test_owner_tags_are_read_concurrently(module, monkeypatch):
    # Read one at a time, a hundred owner tags outlast a clip's scan and validation,
    # so the portal would never show those states.
    fake = install(module, monkeypatch, intake={f"intake/factory-a/jam/{c}.mp4": MINE for c in (A, B, C, D)})
    together = threading.Barrier(4, timeout=5)
    tags = fake.get_object_tagging

    def waits_for_the_others(Bucket, Key):
        together.wait()
        return tags(Bucket, Key)

    fake.get_object_tagging = waits_for_the_others
    assert [u["clip"] for u in ask(module)[1]["uploads"]] == [D, C, B, A]
