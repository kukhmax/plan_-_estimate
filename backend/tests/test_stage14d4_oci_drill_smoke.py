"""Stage 14D.4 — OCI drill-bucket permission smoke (logic, no network, no SDK).

The fake client models Object Storage with versioning and a configurable IAM
policy: the Phase A policy (create + read only) must yield 16/16 PASS, and
every widening of the policy (overwrite, delete, production access, multipart)
or any service error must yield FAIL — never a false PASS.
"""

import sys
import types
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from scripts import stage14d4_oci_drill_smoke as smoke

DRILL, PROD, NS = "plan-estimate-backup-drill", "plan-estimate-backup-prod", "testnamespace"
NAME = "smoke/14d4/20261004T120000Z-abcd1234/probe.bin"
BODY, OTHER = b"probe-bytes" * 100, b"other-bytes" * 100


class FakeServiceError(Exception):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(f"{code}: secret-ish provider message ocid1.tenancy.oc1..leak")
        self.status, self.code = status, code


@dataclass
class Version:
    name: str
    version_id: str
    body: bytes
    is_delete_marker: bool = False


@dataclass
class FakeObjectStorage:
    allow_overwrite: bool = False
    allow_delete: bool = False
    allow_version_delete: bool = False
    allow_multipart: bool = False
    allow_bucket_update: bool = False
    prod_readable: bool = False
    deny_create: bool = False
    versioning: str = "Enabled"
    fail_with: dict[str, Exception] = field(default_factory=dict)
    versions: list[Version] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)

    # helpers
    def _enter(self, op: str, bucket: str) -> None:
        self.calls.append(f"{op}:{bucket}")
        if op in self.fail_with:
            raise self.fail_with[op]
        if bucket == PROD and not self.prod_readable:
            raise FakeServiceError(404, "NotAuthorizedOrNotFound")

    def _live(self, name: str) -> Version | None:
        mine = [v for v in self.versions if v.name == name]
        return None if not mine or mine[-1].is_delete_marker else mine[-1]

    @staticmethod
    def _resp(data: Any = None, headers: dict[str, str] | None = None) -> Any:
        return types.SimpleNamespace(data=data, headers=headers or {})

    # ObjectStorageClient surface used by the smoke
    def get_bucket(self, ns: str, bucket: str) -> Any:
        self._enter("get_bucket", bucket)
        return self._resp(types.SimpleNamespace(versioning=self.versioning))

    def put_object(self, ns: str, bucket: str, name: str, body: bytes, **kw: Any) -> Any:
        self._enter("put_object", bucket)
        exists = self._live(name) is not None
        if not exists and self.deny_create:
            raise FakeServiceError(404, "NotAuthorizedOrNotFound")
        if exists and kw.get("if_none_match") == "*":
            raise FakeServiceError(412, "IfNoneMatchFailed")
        if exists and not self.allow_overwrite:
            raise FakeServiceError(404, "NotAuthorizedOrNotFound")
        self.versions.append(Version(name, f"v{len(self.versions) + 1}", body))
        return self._resp()

    def head_object(self, ns: str, bucket: str, name: str) -> Any:
        self._enter("head_object", bucket)
        live = self._live(name)
        if live is None:
            raise FakeServiceError(404, "ObjectNotFound")
        return self._resp(headers={"content-length": str(len(live.body))})

    def get_object(self, ns: str, bucket: str, name: str) -> Any:
        self._enter("get_object", bucket)
        live = self._live(name)
        if live is None:
            raise FakeServiceError(404, "ObjectNotFound")
        return self._resp(types.SimpleNamespace(content=live.body))

    def list_objects(self, ns: str, bucket: str, prefix: str = "", limit: int | None = None) -> Any:
        self._enter("list_objects", bucket)
        names = sorted({v.name for v in self.versions if v.name.startswith(prefix) and self._live(v.name)})
        return self._resp(types.SimpleNamespace(objects=[types.SimpleNamespace(name=n) for n in names]))

    def list_object_versions(self, ns: str, bucket: str, prefix: str = "") -> Any:
        self._enter("list_object_versions", bucket)
        return self._resp(types.SimpleNamespace(items=[v for v in self.versions if v.name.startswith(prefix)]))

    def delete_object(self, ns: str, bucket: str, name: str, version_id: str | None = None) -> Any:
        self._enter("delete_object", bucket)
        if version_id is None:
            if not self.allow_delete:
                raise FakeServiceError(404, "NotAuthorizedOrNotFound")
            self.versions.append(Version(name, f"v{len(self.versions) + 1}", b"", is_delete_marker=True))
        else:
            if not self.allow_version_delete:
                raise FakeServiceError(404, "NotAuthorizedOrNotFound")
            self.versions = [v for v in self.versions if v.version_id != version_id]
        return self._resp()

    def create_multipart_upload(self, ns: str, bucket: str, details: Any) -> Any:
        self._enter("create_multipart_upload", bucket)
        if not self.allow_multipart:
            raise FakeServiceError(404, "NotAuthorizedOrNotFound")
        return self._resp(types.SimpleNamespace(upload_id="u-1"))

    def abort_multipart_upload(self, ns: str, bucket: str, name: str, upload_id: str) -> Any:
        self._enter("abort_multipart_upload", bucket)
        return self._resp()

    def update_bucket(self, ns: str, bucket: str, details: Any) -> Any:
        self._enter("update_bucket", bucket)
        if not self.allow_bucket_update:
            raise FakeServiceError(404, "NotAuthorizedOrNotFound")
        return self._resp()


def run(client: FakeObjectStorage) -> dict[str, smoke.CheckResult]:
    results = smoke.DrillSmoke(
        client,
        NS,
        DRILL,
        PROD,
        NAME,
        BODY,
        OTHER,
        update_bucket_details=lambda: {"versioning": "Enabled"},
        multipart_details=lambda name: {"object": name},
    ).run()
    return {r.name: r for r in results}


ALL_CHECKS = [
    "drill_get_bucket",
    "drill_versioning_enabled",
    "drill_create_new_object",
    "drill_head_object",
    "drill_get_object",
    "drill_list_objects",
    "drill_list_object_versions",
    "drill_overwrite_existing",
    "drill_conditional_create_existing",
    "drill_delete_object",
    "drill_delete_object_version",
    "drill_object_unchanged",
    "drill_multipart_upload",
    "drill_update_bucket",
    "prod_get_bucket",
    "prod_list_objects",
]


def failed(results: dict[str, smoke.CheckResult]) -> set[str]:
    return {name for name, r in results.items() if not r.passed}


def test_phase_a_policy_passes_every_check():
    client = FakeObjectStorage()
    results = run(client)
    assert list(results) == ALL_CHECKS
    assert failed(results) == set()
    assert results["drill_conditional_create_existing"].detail == "HTTP 412 IfNoneMatchFailed"
    assert [v.body for v in client.versions] == [BODY]  # exactly the probe, nothing else written


def test_production_bucket_is_never_written():
    client = FakeObjectStorage(prod_readable=True)
    run(client)
    prod_calls = [c for c in client.calls if c.endswith(f":{PROD}")]
    assert prod_calls == [f"get_bucket:{PROD}", f"list_objects:{PROD}"]


def test_readable_production_bucket_fails():
    assert failed(run(FakeObjectStorage(prod_readable=True))) == {"prod_get_bucket", "prod_list_objects"}


def test_overwrite_permission_fails_and_is_detected_by_the_invariant():
    results = run(FakeObjectStorage(allow_overwrite=True))
    assert failed(results) == {"drill_overwrite_existing", "drill_object_unchanged"}
    assert "MISMATCH" in results["drill_object_unchanged"].detail
    assert "versions=2" in results["drill_object_unchanged"].detail


def test_delete_permission_fails_and_is_detected_by_the_invariant():
    results = run(FakeObjectStorage(allow_delete=True))
    assert {"drill_delete_object", "drill_object_unchanged"} <= failed(results)


def test_version_delete_permission_fails():
    results = run(FakeObjectStorage(allow_version_delete=True))
    assert {"drill_delete_object_version", "drill_object_unchanged"} <= failed(results)


def test_multipart_permission_fails_and_aborts_the_upload():
    client = FakeObjectStorage(allow_multipart=True)
    results = run(client)
    assert failed(results) == {"drill_multipart_upload"}
    assert "UNEXPECTED" in results["drill_multipart_upload"].detail
    assert f"abort_multipart_upload:{DRILL}" in client.calls


def test_bucket_update_permission_fails():
    assert failed(run(FakeObjectStorage(allow_bucket_update=True))) == {"drill_update_bucket"}


def test_versioning_disabled_fails():
    assert failed(run(FakeObjectStorage(versioning="Disabled"))) == {"drill_versioning_enabled"}


def test_create_denied_skips_object_checks_as_failures():
    results = run(FakeObjectStorage(deny_create=True))
    skipped = {n for n, r in results.items() if r.observed == "skipped"}
    assert len(skipped) == 9
    assert failed(results) == skipped | {"drill_create_new_object"}


def test_server_error_is_never_counted_as_a_denial():
    client = FakeObjectStorage(fail_with={"delete_object": FakeServiceError(503, "ServiceUnavailable")})
    results = run(client)
    assert results["drill_delete_object"].observed == "error"
    assert not results["drill_delete_object"].passed


def test_unexpected_exception_reports_only_its_type():
    client = FakeObjectStorage(fail_with={"update_bucket": RuntimeError("token=SECRET-VALUE")})
    result = run(client)["drill_update_bucket"]
    assert (result.observed, result.detail, result.passed) == ("error", "RuntimeError", False)


def test_report_contains_no_namespace_body_or_provider_message():
    results = list(run(FakeObjectStorage(allow_overwrite=True)).values())
    report = smoke.format_report(results, NAME)
    for leaked in (NS, "probe-bytes", "other-bytes", "ocid1", "secret-ish"):
        assert leaked not in report
    assert report.endswith("RESULT: FAIL (14/16 checks passed)")


@pytest.mark.parametrize(
    ("drill", "prod"),
    [(DRILL, DRILL), ("plan-estimate-backup-prod", "x"), (DRILL, "plan-estimate-backup-drill2")],
)
def test_bucket_guard_refuses_non_drill_targets(drill, prod):
    with pytest.raises(ValueError):
        smoke.validate_buckets(drill, prod)


def test_probe_object_name_is_unique_and_scoped():
    name = smoke.probe_object_name(datetime(2026, 10, 4, 12, 0, tzinfo=UTC), "abcd1234")
    assert name == NAME


def test_main_without_sdk_cannot_run(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "oci", None)
    assert smoke.main(["--namespace", NS]) == smoke.EXIT_CANNOT_RUN
    assert "oci==2.187.1" in capsys.readouterr().err


def _fake_oci(signer: Any) -> types.ModuleType:
    module = types.ModuleType("oci")
    module.auth = types.SimpleNamespace(signers=types.SimpleNamespace(InstancePrincipalsSecurityTokenSigner=signer))  # type: ignore[attr-defined]
    return module


def test_main_reports_missing_instance_principal(monkeypatch, capsys):
    def no_principal() -> None:
        raise ConnectionRefusedError("169.254.169.254 refused")

    monkeypatch.setitem(sys.modules, "oci", _fake_oci(no_principal))
    assert smoke.main(["--auth-only"]) == smoke.EXIT_NO_PRINCIPAL
    assert capsys.readouterr().out.strip() == "instance principal: NOT obtainable (ConnectionRefusedError)"


def test_main_auth_only_makes_no_object_storage_call(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "oci", _fake_oci(lambda: object()))
    assert smoke.main(["--auth-only"]) == smoke.EXIT_PASS
    assert capsys.readouterr().out.strip() == "instance principal: obtained"


def test_main_requires_namespace_for_the_full_smoke(monkeypatch):
    monkeypatch.setitem(sys.modules, "oci", _fake_oci(lambda: object()))
    monkeypatch.delenv("OCI_NAMESPACE", raising=False)
    assert smoke.main([]) == smoke.EXIT_CANNOT_RUN
