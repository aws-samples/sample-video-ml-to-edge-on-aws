# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import json
import re
from urllib.parse import parse_qs, urlparse

import pytest

from conftest import ROOT, import_from

ENV = {"INTAKE_BUCKET": "intake-bucket", "LABELS": "normal,jam,drop,empty",
       "SITES": "factory-a,factory-b", "MAX_BYTES": "1000"}


@pytest.fixture(scope="module")
def presign():
    return import_from(ROOT / "lambdas" / "presign", "handler", ENV)


def call(presign, body, groups="[factory-a]"):
    event = {"body": json.dumps(body),
             "requestContext": {"authorizer": {"jwt": {"claims": {"cognito:groups": groups, "sub": "sub-123",
                                                                  "cognito:username": "contributor-a"}}}}}
    response = presign.main(event, None)
    return response["statusCode"], json.loads(response["body"])


def test_key_uses_site_from_group_and_signs_content_length(presign):
    status, body = call(presign, {"label": "jam", "size": 512, "filename": "../../secret.mp4", "site": "factory-b"})
    assert status == 200
    assert re.fullmatch(r"intake/factory-a/jam/[0-9a-f]{32}\.mp4", body["key"])
    url = urlparse(body["url"])
    assert url.path == "/" + body["key"]
    signed = parse_qs(url.query)["X-Amz-SignedHeaders"][0].split(";")
    assert "content-length" in signed and "x-amz-tagging" in signed
    assert body["headers"] == {"Content-Type": "video/mp4", "x-amz-tagging": "contributor=sub-123"}


def test_groups_claim_as_list(presign):
    assert call(presign, {"label": "jam", "size": 1}, groups=["factory-b"])[1]["key"].startswith("intake/factory-b/")


@pytest.mark.parametrize("groups", ["[]", "[factory-a factory-b]", "[admins]", ""])
def test_caller_needs_exactly_one_site_group(presign, groups):
    assert call(presign, {"label": "jam", "size": 1}, groups=groups)[0] == 403


@pytest.mark.parametrize("body", [{"label": "fire", "size": 1}, {"size": 1}, {"label": "jam", "size": 0},
                                  {"label": "jam", "size": 1001}, {"label": "jam", "size": True},
                                  {"label": "jam", "size": "10"}])
def test_rejects_bad_label_or_size(presign, body):
    assert call(presign, body)[0] == 400


def test_rejects_non_object_body(presign):
    event = {"body": "[1]", "requestContext": {"authorizer": {"jwt": {"claims": {"cognito:groups": "[factory-a]"}}}}}
    assert presign.main(event, None)["statusCode"] == 400


def test_issued_url_is_logged_with_the_caller(presign, capsys):
    call(presign, {"label": "jam", "size": 1})
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert (line["user"], line["username"], line["site"]) == ("sub-123", "contributor-a", "factory-a")
