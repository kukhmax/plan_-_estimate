"""Stage 14D.4.6 — OCI restore-principal smoke (logic, no network, no SDK).

The fake client models the drill and production buckets with a configurable IAM
policy: the restore policy (read only) must yield 12/12 PASS; every widening
(any write permission) or narrowing (a bucket not readable) must yield FAIL —
never a false PASS. Production is only ever read.
"""

import sys
import types
from dataclasses import dataclass, field
from typing import Any

import pytest

from scripts import stage14d4_oci_restore_smoke as smoke

DRILL, PROD, NS = "plan-estimate-backup-drill", "plan-estimate-backup-prod", "testnamespace"
PROBE = "smoke/14d4/20261004T141338Z-68bcaee7/probe.bin"
WRITE_NAME = f"{smoke.WRITE_DENIED_PREFIX}abcd1234.bin"


class FakeServiceError(Exception):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(f"{code}: provider message ocid1.user.oc1..leak")
        self.status, self.code = status, code


@dataclass
class FakeObjectStorage:
    can_put: bool = False
    can_delete: bool = False
    can_multipart: bool = False
    can_update_bucket: bool = False
    can_read_prod: bool = True
    can_read_drill: bool = True
    probe_size: int = smoke.PROBE_BYTES
    extra_versions: int = 0
    fail_with: dict[str, Exception] = field(default_factory=dict)
    objects: dict[str, int] = field(default_factory=lambda: {PROBE: smoke.PROBE_BYTES})
    deleted: bool = False
    calls: list[str] = field(default_factory=list)

    def _enter(self, op: str, bucket: str, read: bool = True) -> None:
        self.calls.append(f"{op}:{bucket}")
        if op in self.fail_with:
            raise self.fail_with[op]
        if read and not (self.can_read_prod if bucket == PROD else self.can_read_drill):
            raise FakeServiceError(404, "BucketNotFound")

    @staticmethod
    def _resp(data: Any = None, headers: dict[str, str] | None = None) -> Any:
        return types.SimpleNamespace(data=data, headers=headers or {})

    def get_bucket(self, ns: str, bucket: str) -> Any:
        self._enter("get_bucket", bucket)
        return self._resp(types.SimpleNamespace(versioning="Enabled"))

    def list_objects(self, ns: str, bucket: str, prefix: str = "", limit: int | None = None) -> Any:
        self._enter("list_objects", bucket)
        names = [n for n in sorted(self.objects) if n.startswith(prefix)] if bucket == DRILL else []
        return self._resp(types.SimpleNamespace(objects=[types.SimpleNamespace(name=n) for n in names]))

    def head_object(self, ns: str, bucket: str, name: str) -> Any:
        self._enter("head_object", bucket)
        if name not in self.objects:
            raise FakeServiceError(404, "ObjectNotFound")
        return self._resp(headers={"content-length": str(self.probe_size)})

    def get_object(self, ns: str, bucket: str, name: str) -> Any:
        self._enter("get_object", bucket)
        return self._resp(types.SimpleNamespace(content=b"x" * self.probe_size))

    def list_object_versions(self, ns: str, bucket: str, prefix: str = "") -> Any:
        self._enter("list_object_versions", bucket)
        items = [
            types.SimpleNamespace(name=n, version_id=f"v{i}", is_delete_marker=False)
            for n in self.objects
            if n.startswith(prefix) and n == PROBE and not self.deleted
            for i in range(1 + self.extra_versions)
        ]
        return self._resp(types.SimpleNamespace(items=items))

    def put_object(self, ns: str, bucket: str, name: str, body: bytes) -> Any:
        self._enter("put_object", bucket, read=False)
        if not self.can_put:
            raise FakeServiceError(404, "BucketNotFound")
        self.objects[name] = len(body)
        return self._resp()

    def delete_object(self, ns: str, bucket: str, name: str) -> Any:
        self._enter("delete_object", bucket, read=False)
        if not self.can_delete:
            raise FakeServiceError(404, "BucketNotFound")
        self.deleted = True
        self.objects.pop(name, None)
        return self._resp()

    def create_multipart_upload(self, ns: str, bucket: str, details: Any) -> Any:
        self._enter("create_multipart_upload", bucket, read=False)
        if not self.can_multipart:
            raise FakeServiceError(404, "BucketNotFound")
        return self._resp(types.SimpleNamespace(upload_id="u-1"))

    def abort_multipart_upload(self, ns: str, bucket: str, name: str, upload_id: str) -> Any:
        self._enter("abort_multipart_upload", bucket, read=False)
        return self._resp()

    def update_bucket(self, ns: str, bucket: str, details: Any) -> Any:
        self._enter("update_bucket", bucket, read=False)
        if not self.can_update_bucket:
            raise FakeServiceError(404, "BucketNotFound")
        return self._resp()


def run(client: FakeObjectStorage, probe: str = PROBE) -> dict[str, smoke.CheckResult]:
    results = smoke.RestoreSmoke(
        client,
        NS,
        DRILL,
        PROD,
        probe,
        WRITE_NAME,
        update_bucket_details=lambda: {"versioning": "Enabled"},
        multipart_details=lambda name: {"object": name},
    ).run()
    return {r.name: r for r in results}


def failed(results: dict[str, smoke.CheckResult]) -> set[str]:
    return {name for name, r in results.items() if not r.passed}


ALL_CHECKS = [
    "restore_get_bucket[drill]",
    "restore_get_bucket[prod]",
    "restore_list_objects[drill]",
    "restore_list_objects[prod]",
    "restore_head_probe",
    "restore_get_probe",
    "restore_put_new_object[drill]",
    "restore_delete_probe[drill]",
    "restore_multipart_upload[drill]",
    "restore_update_bucket[drill]",
    "restore_probe_unchanged",
    "restore_denied_write_absent",
]


def test_read_only_restore_policy_passes_every_check():
    client = FakeObjectStorage()
    results = run(client)
    assert list(results) == ALL_CHECKS
    assert failed(results) == set()
    assert client.objects == {PROBE: smoke.PROBE_BYTES}


def test_production_bucket_is_only_ever_read():
    client = FakeObjectStorage(can_put=True, can_delete=True, can_multipart=True, can_update_bucket=True)
    run(client)
    prod_ops = {c.split(":")[0] for c in client.calls if c.endswith(f":{PROD}")}
    assert prod_ops == {"get_bucket", "list_objects"}


def test_put_permission_fails_and_the_absence_invariant_catches_the_object():
    results = run(FakeObjectStorage(can_put=True))
    assert failed(results) == {"restore_put_new_object[drill]", "restore_denied_write_absent"}


def test_delete_permission_fails_and_the_unchanged_invariant_catches_it():
    results = run(FakeObjectStorage(can_delete=True))
    assert failed(results) == {"restore_delete_probe[drill]", "restore_probe_unchanged"}


def test_multipart_permission_fails_and_aborts_the_upload():
    client = FakeObjectStorage(can_multipart=True)
    results = run(client)
    assert failed(results) == {"restore_multipart_upload[drill]"}
    assert "UNEXPECTED" in results["restore_multipart_upload[drill]"].detail
    assert f"abort_multipart_upload:{DRILL}" in client.calls


def test_bucket_update_permission_fails():
    assert failed(run(FakeObjectStorage(can_update_bucket=True))) == {"restore_update_bucket[drill]"}


def test_unreadable_production_bucket_fails():
    assert failed(run(FakeObjectStorage(can_read_prod=False))) == {
        "restore_get_bucket[prod]",
        "restore_list_objects[prod]",
    }


def test_unreadable_drill_bucket_fails_everything_that_reads_it():
    results = run(FakeObjectStorage(can_read_drill=False))
    assert {
        "restore_get_bucket[drill]",
        "restore_list_objects[drill]",
        "restore_head_probe",
        "restore_get_probe",
        "restore_probe_unchanged",
        "restore_denied_write_absent",
    } <= failed(results)


def test_wrong_probe_size_fails():
    assert {"restore_head_probe", "restore_get_probe"} <= failed(run(FakeObjectStorage(probe_size=10)))


def test_second_version_of_the_probe_fails_the_invariant():
    assert failed(run(FakeObjectStorage(extra_versions=1))) == {"restore_probe_unchanged"}


def test_server_error_is_never_counted_as_a_denial():
    client = FakeObjectStorage(fail_with={"delete_object": FakeServiceError(503, "ServiceUnavailable")})
    result = run(client)["restore_delete_probe[drill]"]
    assert (result.observed, result.passed) == ("error", False)


def test_unexpected_exception_reports_only_its_type():
    client = FakeObjectStorage(fail_with={"update_bucket": RuntimeError("key=SECRET-VALUE")})
    result = run(client)["restore_update_bucket[drill]"]
    assert (result.observed, result.detail, result.passed) == ("error", "RuntimeError", False)


def test_report_contains_no_namespace_or_provider_message():
    report = smoke.format_report(list(run(FakeObjectStorage(can_put=True)).values()))
    for leaked in (NS, "ocid1", "provider message", "restore-write-attempt"):
        assert leaked not in report
    assert report.endswith("RESULT: FAIL (10/12 checks passed)")


@pytest.mark.parametrize(
    "probe",
    ["probe.bin", "smoke/14d4/x/other.bin", "smoke/14d4/../prod/probe.bin", "photos/v1/a/probe.bin"],
)
def test_probe_object_name_is_validated(probe):
    with pytest.raises(ValueError):
        run(FakeObjectStorage(), probe=probe)


@pytest.mark.parametrize(("drill", "prod"), [(DRILL, DRILL), (PROD, "x"), (DRILL, "plan-estimate-backup-drill2")])
def test_bucket_guard_refuses_non_drill_targets(drill, prod):
    with pytest.raises(ValueError):
        smoke.validate_buckets(drill, prod)


def test_denied_write_name_must_stay_in_its_prefix():
    with pytest.raises(ValueError):
        smoke.RestoreSmoke(
            FakeObjectStorage(), NS, DRILL, PROD, PROBE, "photos/v1/x/original.jpg", dict, lambda n: {}
        )


def test_main_without_sdk_cannot_run(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "oci", None)
    assert smoke.main(["--probe-object", PROBE]) == smoke.EXIT_CANNOT_RUN
    assert "oci==2.187.1" in capsys.readouterr().err


def test_main_requires_namespace_and_config(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "oci", types.ModuleType("oci"))
    monkeypatch.delenv("OCI_NAMESPACE", raising=False)
    monkeypatch.delenv("OCI_CONFIG_FILE", raising=False)
    assert smoke.main(["--probe-object", PROBE]) == smoke.EXIT_CANNOT_RUN
    assert "--namespace and --config" in capsys.readouterr().err


def test_main_config_errors_report_only_the_exception_type(monkeypatch, capsys):
    def bad_config(path: str, profile: str) -> dict:
        raise FileNotFoundError(f"/home/secret/{path}")

    fake = types.ModuleType("oci")
    fake.config = types.SimpleNamespace(from_file=bad_config)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "oci", fake)
    assert smoke.main(["--namespace", NS, "--config", "nowhere", "--probe-object", PROBE]) == smoke.EXIT_CANNOT_RUN
    err = capsys.readouterr().err
    assert "FileNotFoundError" in err and "secret" not in err
