"""Stage 14D.4 — R2 drill-token smoke (logic + botocore model contract, no network).

A fake S3 client models a correctly scoped drill token and every way it can be
wrong (unscoped token, ignored If-None-Match, failed cleanup); only the correct
token yields PASS. A botocore Stubber run checks every request parameter
against the real S3 service model of the pinned boto3.
"""

import io
import types
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from botocore.exceptions import ClientError
from botocore.stub import ANY, Stubber

from scripts import stage14d4_r2_drill_smoke as smoke

ACCOUNT = "0123456789abcdef0123456789abcdef"
ENV = {
    "R2_ENDPOINT_URL": f"https://{ACCOUNT}.eu.r2.cloudflarestorage.com",
    "R2_ACCESS_KEY_ID": "AKID-NOT-REAL",
    "R2_SECRET_ACCESS_KEY": "SECRET-NOT-REAL",
    "R2_BUCKET": "plan-estimate-media-drill-source",
    "R2_FORBIDDEN_BUCKETS": "plan-estimate-media-prod, plan-estimate-media-drill-restore",
}
BUCKET = ENV["R2_BUCKET"]
FORBIDDEN = ("plan-estimate-media-prod", "plan-estimate-media-drill-restore")
KEY = "smoke/14d4/20261004T120000Z-abcd1234/probe.bin"
BODY = b"probe" * 1000


def client_error(status: int, code: str, op: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": f"provider message for account {ACCOUNT}"}, "ResponseMetadata": {"HTTPStatusCode": status}},
        op,
    )


@dataclass
class FakeS3:
    scoped: bool = True
    honour_if_none_match: bool = True
    allow_delete: bool = True
    objects: dict[str, bytes] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def _scope(self, op: str, bucket: str) -> None:
        self.calls.append(f"{op}:{bucket}")
        if bucket != BUCKET and self.scoped:
            raise client_error(403, "AccessDenied", op)

    def put_object(self, Bucket: str, Key: str, Body: bytes, **kw: Any) -> dict:
        self._scope("put_object", Bucket)
        if Key in self.objects and kw.get("IfNoneMatch") == "*" and self.honour_if_none_match:
            raise client_error(412, "PreconditionFailed", "PutObject")
        self.objects[Key] = Body
        return {}

    def head_object(self, Bucket: str, Key: str) -> dict:
        self._scope("head_object", Bucket)
        if Key not in self.objects:
            raise client_error(404, "404", "HeadObject")
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, Bucket: str, Key: str) -> dict:
        self._scope("get_object", Bucket)
        return {"Body": io.BytesIO(self.objects[Key])}

    def list_objects_v2(self, Bucket: str, Prefix: str = "", MaxKeys: int = 1000) -> dict:
        self._scope("list_objects_v2", Bucket)
        return {"Contents": [{"Key": k} for k in sorted(self.objects) if k.startswith(Prefix)]}

    def head_bucket(self, Bucket: str) -> dict:
        self._scope("head_bucket", Bucket)
        return {}

    def delete_object(self, Bucket: str, Key: str) -> dict:
        self._scope("delete_object", Bucket)
        if self.allow_delete:
            self.objects.pop(Key, None)
        return {}


def run(client: Any) -> dict[str, smoke.CheckResult]:
    return {r.name: r for r in smoke.R2DrillSmoke(client, BUCKET, FORBIDDEN, KEY, BODY).run()}


def failed(results: dict[str, smoke.CheckResult]) -> set[str]:
    return {n for n, r in results.items() if not r.passed}


def test_correctly_scoped_drill_token_passes_and_cleans_up():
    client = FakeS3()
    results = run(client)
    assert failed(results) == set()
    assert len(results) == 8 + 2 * len(FORBIDDEN)
    assert results["r2_conditional_create_existing"].detail == "HTTP 412 PreconditionFailed"
    assert client.objects == {}


def test_nothing_is_ever_written_to_a_forbidden_bucket():
    client = FakeS3(scoped=False)
    run(client)
    for bucket in FORBIDDEN:
        assert {c.split(":")[0] for c in client.calls if c.endswith(f":{bucket}")} == {"list_objects_v2", "head_bucket"}


def test_unscoped_token_fails():
    results = run(FakeS3(scoped=False))
    assert failed(results) == {f"r2_forbidden_{op}[{b}]" for b in FORBIDDEN for op in ("list", "head_bucket")}


def test_ignored_if_none_match_fails_and_the_invariant_catches_the_overwrite():
    results = run(FakeS3(honour_if_none_match=False))
    assert failed(results) == {"r2_conditional_create_existing", "r2_object_unchanged"}


def test_failed_cleanup_is_reported():
    results = run(FakeS3(allow_delete=False))
    assert failed(results) == {"r2_cleanup_verified"}


def test_report_never_contains_credentials_endpoint_or_body():
    results = list(run(FakeS3(scoped=False)).values())
    report = smoke.format_report(results, BUCKET, KEY)
    for leaked in (ACCOUNT, "AKID-NOT-REAL", "SECRET-NOT-REAL", "probeprobe", "provider message"):
        assert leaked not in report


def test_config_repr_hides_credentials_and_account():
    text = repr(smoke.load_config(ENV))
    for leaked in (ACCOUNT, "AKID-NOT-REAL", "SECRET-NOT-REAL"):
        assert leaked not in text


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"R2_ENDPOINT_URL": f"https://{ACCOUNT}.r2.cloudflarestorage.com"}, "EU-jurisdiction"),
        ({"R2_ENDPOINT_URL": f"http://{ACCOUNT}.eu.r2.cloudflarestorage.com"}, "EU-jurisdiction"),
        ({"R2_SECRET_ACCESS_KEY": ""}, "required"),
        ({"R2_BUCKET": "plan-estimate-media-prod"}, "not a drill bucket"),
        ({"R2_FORBIDDEN_BUCKETS": ""}, "at least one"),
        ({"R2_FORBIDDEN_BUCKETS": BUCKET}, "must not be listed"),
        ({"R2_FORBIDDEN_BUCKETS": "Bad_Name"}, "invalid bucket name"),
    ],
)
def test_config_refuses_unsafe_settings(override, message):
    with pytest.raises(ValueError, match=message):
        smoke.load_config({**ENV, **override})


def test_main_refuses_bad_config_without_echoing_secrets(capsys):
    assert smoke.main([], env={**ENV, "R2_BUCKET": "plan-estimate-media-prod"}) == smoke.EXIT_CANNOT_RUN
    captured = capsys.readouterr()
    assert "not a drill bucket" in captured.err
    assert "SECRET-NOT-REAL" not in captured.out + captured.err


def test_probe_key_format():
    assert smoke.probe_key(datetime(2026, 10, 4, 12, 0, tzinfo=UTC), "abcd1234") == KEY


def test_requests_match_the_real_s3_model_of_the_pinned_boto3():
    """Every call of the success path validated by botocore against the S3 model."""
    client = smoke.build_client(smoke.load_config(ENV))
    stubber = Stubber(client)
    stubber.add_response(
        "put_object",
        {},
        {
            "Bucket": BUCKET,
            "Key": KEY,
            "Body": BODY,
            "IfNoneMatch": "*",
            "ContentMD5": ANY,
            "ContentLength": len(BODY),
            "ContentType": "application/octet-stream",
        },
    )
    stubber.add_response("head_object", {"ContentLength": len(BODY)}, {"Bucket": BUCKET, "Key": KEY})
    body = types.SimpleNamespace(read=lambda: BODY)
    stubber.add_response("get_object", {"Body": body}, {"Bucket": BUCKET, "Key": KEY})  # type: ignore[dict-item]
    stubber.add_response("list_objects_v2", {"Contents": [{"Key": KEY}]}, {"Bucket": BUCKET, "Prefix": KEY})
    stubber.add_client_error(
        "put_object",
        service_error_code="PreconditionFailed",
        http_status_code=412,
        expected_params={"Bucket": BUCKET, "Key": KEY, "Body": ANY, "IfNoneMatch": "*"},
    )
    stubber.add_response("get_object", {"Body": body}, {"Bucket": BUCKET, "Key": KEY})  # type: ignore[dict-item]
    stubber.add_response("delete_object", {}, {"Bucket": BUCKET, "Key": KEY})
    stubber.add_client_error(
        "head_object", service_error_code="404", http_status_code=404, expected_params={"Bucket": BUCKET, "Key": KEY}
    )
    for bucket in FORBIDDEN:
        stubber.add_client_error(
            "list_objects_v2",
            service_error_code="AccessDenied",
            http_status_code=403,
            expected_params={"Bucket": bucket, "MaxKeys": 1},
        )
        stubber.add_client_error(
            "head_bucket", service_error_code="403", http_status_code=403, expected_params={"Bucket": bucket}
        )
    with stubber:
        results = run(client)
    stubber.assert_no_pending_responses()
    assert failed(results) == set()
