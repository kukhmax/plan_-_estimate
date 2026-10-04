"""Stage 14D.2F — OCI backup target adapter (fake SDK client, no network, no SDK needed)."""

import base64
import hashlib
import stat
import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.backup import manifest as mf
from app.backup import oci_target as ot
from app.backup import target as tg
from app.domain.exceptions import (
    MediaObjectConflict,
    MediaObjectNotFound,
    MediaStorageMisconfigured,
    MediaStorageUnavailable,
)
from tests.test_stage14d2e_manifest import RUN, make_header

NS, BUCKET = "testnamespace", "plan-estimate-backup-drill"
DATA = b"oracle-object-" * 400


class ServiceError(Exception):
    """Shape of oci.exceptions.ServiceError: HTTP status + code (None for body-less answers)."""

    def __init__(self, status: int, code: str | None) -> None:
        super().__init__(f"{status} {code}: message with ocid1.tenancy.oc1..leak and a token")
        self.status, self.code = status, code


def transport_error(name: str, module: str, base: type[BaseException] = Exception) -> Exception:
    error_class = type(name, (base,), {"__module__": module})
    return error_class("connection broke")  # type: ignore[no-any-return]


class Raw:
    def __init__(self, chunks: list[bytes], fail_with: Exception | None = None) -> None:
        self.chunks, self.fail_with = chunks, fail_with
        self.stream_args: tuple[int, bool] | None = None

    def stream(self, size: int, decode_content: bool) -> Any:
        self.stream_args = (size, decode_content)
        yield from self.chunks
        if self.fail_with is not None:
            raise self.fail_with


class FakeClient:
    """The only three SDK calls the adapter may use. Anything else is an AttributeError."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail: dict[str, Exception] = {}
        self.chunk_size = 700
        self.truncate_by = 0
        self.stream_error: Exception | None = None
        self.head_headers: dict[str, str] | None = None
        self.last_raw: Raw | None = None

    def put_object(self, namespace: str, bucket: str, key: str, body: Any, **kwargs: Any) -> Any:
        data = body.read()
        self.calls.append(("put_object", {"ns": namespace, "bucket": bucket, "key": key, "data": data, **kwargs}))
        if "put_object" in self.fail:
            raise self.fail["put_object"]
        if key in self.objects:
            if kwargs.get("if_none_match") == "*":
                raise ServiceError(412, "IfNoneMatchFailed")
            raise ServiceError(404, "BucketNotFound")  # OCI masks a missing OBJECT_OVERWRITE as 404
        self.objects[key] = data
        return types.SimpleNamespace(status=200)

    def head_object(self, namespace: str, bucket: str, key: str) -> Any:
        self.calls.append(("head_object", {"key": key}))
        if "head_object" in self.fail:
            raise self.fail["head_object"]
        if key not in self.objects:
            raise ServiceError(404, None)  # HEAD answers have no body, hence no code
        headers = {"content-length": str(len(self.objects[key])), "etag": "opaque-etag"}
        return types.SimpleNamespace(headers=self.head_headers if self.head_headers is not None else headers)

    def get_object(self, namespace: str, bucket: str, key: str) -> Any:
        self.calls.append(("get_object", {"key": key}))
        if "get_object" in self.fail:
            raise self.fail["get_object"]
        if key not in self.objects:
            raise ServiceError(404, "ObjectNotFound")
        data = self.objects[key]
        chunks = [data[i : i + self.chunk_size] for i in range(0, len(data), self.chunk_size)]
        self.last_raw = Raw(chunks, self.stream_error)
        length = len(data) - self.truncate_by
        return types.SimpleNamespace(headers={"content-length": str(length)}, data=types.SimpleNamespace(raw=self.last_raw))


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def target(client: FakeClient) -> ot.OciBackupTarget:
    return ot.OciBackupTarget(namespace=NS, bucket=BUCKET, client=client)


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "source.bin"
    path.write_bytes(DATA)
    return path


# --- construction ------------------------------------------------------------------------------


@pytest.mark.parametrize("namespace", ["", "has space", "x" * 64, "a/b", "ünï"])
def test_namespace_is_validated(namespace):
    with pytest.raises(ValueError):
        ot.OciBackupTarget(namespace=namespace, bucket=BUCKET, client=object())


@pytest.mark.parametrize("bucket", ["", "A", "Bucket_1", "-bucket", "x" * 64, "a b"])
def test_bucket_is_validated(bucket):
    with pytest.raises(ValueError):
        ot.OciBackupTarget(namespace=NS, bucket=bucket, client=object())


def test_repr_never_exposes_the_namespace(target):
    assert NS not in repr(target) and BUCKET in repr(target)


def test_public_surface_is_the_create_only_port(target):
    public = {name for name in dir(target) if not name.startswith("_")}
    assert public == {"put_new", "head", "download_to", "from_instance_principal"}
    assert isinstance(target, tg.BackupTarget)


# --- put_new ------------------------------------------------------------------------------------


async def test_put_new_sends_exactly_the_proven_create_only_request(target, client, source):
    assert await target.put_new("db/x/dump.age", source, "application/octet-stream") is tg.PutOutcome.CREATED
    (name, call), = client.calls
    assert name == "put_object" and call["data"] == DATA
    assert (call["ns"], call["bucket"], call["key"]) == (NS, BUCKET, "db/x/dump.age")
    assert {k: v for k, v in call.items() if k not in ("ns", "bucket", "key", "data")} == {
        "content_length": len(DATA),
        "content_type": "application/octet-stream",
        "content_md5": base64.b64encode(hashlib.md5(DATA).digest()).decode(),
        "if_none_match": "*",
    }


async def test_an_existing_object_is_reported_not_overwritten(target, client, source):
    client.objects["k/a"] = b"first"
    assert await target.put_new("k/a", source, "text/plain") is tg.PutOutcome.EXISTS
    assert client.objects["k/a"] == b"first"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ServiceError(503, "ServiceUnavailable"), MediaStorageUnavailable),
        (ServiceError(500, None), MediaStorageUnavailable),
        (ServiceError(429, "TooManyRequests"), MediaStorageUnavailable),
        (ServiceError(408, "RequestTimeout"), MediaStorageUnavailable),
        (ServiceError(400, "Throttled"), MediaStorageUnavailable),
        (ServiceError(404, "BucketNotFound"), MediaStorageMisconfigured),  # masked denial
        (ServiceError(404, "NamespaceNotFound"), MediaStorageMisconfigured),
        (ServiceError(404, "NotAuthorizedOrNotFound"), MediaStorageMisconfigured),
        (ServiceError(401, "NotAuthenticated"), MediaStorageMisconfigured),
        (ServiceError(403, None), MediaStorageMisconfigured),
        (ServiceError(400, "InvalidDigest"), MediaStorageMisconfigured),
        (ServiceError(409, "Conflict"), MediaStorageMisconfigured),
        (transport_error("ReadTimeout", "oci._vendor.requests.exceptions", OSError), MediaStorageUnavailable),
        (transport_error("ConnectionError", "requests.exceptions", OSError), MediaStorageUnavailable),
        (transport_error("ProtocolError", "urllib3.exceptions"), MediaStorageUnavailable),
        (transport_error("SSLError", "ssl", OSError), MediaStorageUnavailable),
        (ConnectionResetError("reset"), MediaStorageUnavailable),
        (TimeoutError("timed out"), MediaStorageUnavailable),
    ],
)
async def test_provider_failures_are_mapped_without_leaking_details(target, client, source, error, expected):
    client.fail["put_object"] = error
    with pytest.raises(expected) as caught:
        await target.put_new("k/a", source, "text/plain")
    text = f"{caught.value} {caught.value.error_code}"
    assert "ocid1" not in text and "token" not in text and "message with" not in text


@pytest.mark.parametrize(
    "error",
    [
        transport_error("InvalidConfig", "oci.exceptions"),  # SDK configuration problem, not a transport error
        PermissionError("local"),
        RuntimeError("bug"),
        KeyError("bug"),
    ],
)
async def test_local_and_programming_errors_propagate_unchanged(target, client, source, error):
    client.fail["put_object"] = error
    with pytest.raises(type(error)):
        await target.put_new("k/a", source, "text/plain")


async def test_missing_or_empty_sources_are_not_mapped(target, tmp_path):
    with pytest.raises(FileNotFoundError):
        await target.put_new("k/a", tmp_path / "missing", "text/plain")
    empty = tmp_path / "empty"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        await target.put_new("k/a", empty, "text/plain")


async def test_keys_are_validated_before_any_call(target, client, source):
    for bad in ("", "/abs", "a/../b", "a//b"):
        with pytest.raises(ValueError):
            await target.put_new(bad, source, "text/plain")
        with pytest.raises(ValueError):
            await target.head(bad)
        with pytest.raises(ValueError):
            await target.download_to(bad, source.parent / "x")
    assert client.calls == []


# --- head ---------------------------------------------------------------------------------------


async def test_head_reports_size_and_opaque_etag(target, client):
    client.objects["k/a"] = DATA
    assert await target.head("k/a") == tg.TargetObject(size=len(DATA), etag="opaque-etag")


@pytest.mark.parametrize("code", [None, "ObjectNotFound", "NotFound"])
async def test_a_missing_object_is_none(target, code):
    target._client.fail["head_object"] = ServiceError(404, code)
    assert await target.head("k/a") is None


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ServiceError(404, "BucketNotFound"), MediaStorageMisconfigured),
        (ServiceError(403, None), MediaStorageMisconfigured),
        (ServiceError(503, None), MediaStorageUnavailable),
    ],
)
async def test_head_distinguishes_absence_from_denial_and_outage(target, error, expected):
    target._client.fail["head_object"] = error
    with pytest.raises(expected):
        await target.head("k/a")


@pytest.mark.parametrize("headers", [{}, {"content-length": "abc"}, {"content-length": "-1"}])
async def test_head_without_a_valid_size_is_a_transient_failure(target, client, headers):
    client.objects["k/a"] = DATA
    client.head_headers = headers
    with pytest.raises(MediaStorageUnavailable):
        await target.head("k/a")


# --- download -----------------------------------------------------------------------------------


async def test_download_streams_into_a_new_private_file(target, client, tmp_path):
    client.objects["k/a"] = DATA
    destination = tmp_path / "out"
    await target.download_to("k/a", destination)
    assert destination.read_bytes() == DATA
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert client.last_raw is not None and client.last_raw.stream_args == (tg.CHUNK_BYTES, False)


async def test_download_never_replaces_an_existing_file(target, client, tmp_path):
    client.objects["k/a"] = DATA
    destination = tmp_path / "out"
    destination.write_bytes(b"precious")
    with pytest.raises(FileExistsError):
        await target.download_to("k/a", destination)
    assert destination.read_bytes() == b"precious"


async def test_a_short_download_is_transient_and_leaves_no_partial_file(target, client, tmp_path):
    client.objects["k/a"] = DATA
    client.truncate_by = -5  # the server promised 5 more bytes than it sent
    destination = tmp_path / "out"
    with pytest.raises(MediaStorageUnavailable, match="incomplete"):
        await target.download_to("k/a", destination)
    assert not destination.exists()


async def test_a_dropped_connection_mid_download_leaves_no_partial_file(target, client, tmp_path):
    client.objects["k/a"] = DATA
    client.stream_error = transport_error("ChunkedEncodingError", "requests.exceptions", OSError)
    destination = tmp_path / "out"
    with pytest.raises(MediaStorageUnavailable):
        await target.download_to("k/a", destination)
    assert not destination.exists()


async def test_download_error_mapping(target, client, tmp_path):
    with pytest.raises(MediaObjectNotFound):
        await target.download_to("k/missing", tmp_path / "a")
    client.fail["get_object"] = ServiceError(404, "BucketNotFound")
    with pytest.raises(MediaStorageMisconfigured):
        await target.download_to("k/a", tmp_path / "b")
    client.fail["get_object"] = ServiceError(500, None)
    with pytest.raises(MediaStorageUnavailable):
        await target.download_to("k/a", tmp_path / "c")


# --- only the three safe SDK calls are ever made ---------------------------------------------------


async def test_the_adapter_uses_nothing_but_put_head_and_get(target, client, source, tmp_path):
    await target.put_new("k/a", source, "text/plain")
    await target.head("k/a")
    await target.download_to("k/a", tmp_path / "out")
    assert {name for name, _ in client.calls} == {"put_object", "head_object", "get_object"}
    assert all("version_id" not in call and "if_match" not in call for _, call in client.calls)


# --- error mapping table ------------------------------------------------------------------------------


def test_map_oci_error_refuses_to_map_unrelated_exceptions():
    for error in (ValueError("x"), RuntimeError("x"), FileExistsError("x"), transport_error("Whatever", "mymodule")):
        with pytest.raises(TypeError):
            ot.map_oci_error(error)


def test_service_error_facts_shape():
    assert ot.service_error_facts(ServiceError(404, None)) == (404, None)
    assert ot.service_error_facts(ServiceError(412, "IfNoneMatchFailed")) == (412, "IfNoneMatchFailed")
    assert ot.service_error_facts(ValueError("x")) is None


# --- the adapter under the verified-put and publication logic ---------------------------------------------


async def test_verified_put_through_the_real_adapter(target, client, source, tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)

    async def instant(_: float) -> None:
        return None

    common: dict[str, Any] = {"scratch_dir": scratch, "sleep": instant, "content_type": "application/octet-stream"}
    first = await tg.put_verified(target, key="smoke/a", source=source, **common)
    again = await tg.put_verified(target, key="smoke/a", source=source, **common)
    assert (first.created, again.created) == (True, False)
    other = tmp_path / "other.bin"
    other.write_bytes(b"different bytes entirely")
    with pytest.raises(MediaObjectConflict):
        await tg.put_verified(target, key="smoke/a", source=other, **common)
    assert client.objects["smoke/a"] == DATA
    assert list(scratch.iterdir()) == []


async def test_publication_through_the_real_adapter(target, client, tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)
    dump = tmp_path / "plan-estimate.sql.gz.age"
    dump.write_bytes(b"encrypted-dump-" * 2000)
    base = make_header([])
    header = mf.ManifestHeader(
        run_id=RUN,
        started_at=base.started_at,
        tool_commit=base.tool_commit,
        source=base.source,
        target=base.target,
        db_dump=mf.DbDumpInfo(
            key=mf.db_dump_key(RUN),
            recipients=base.db_dump.recipients,
            encrypted_sha256=hashlib.sha256(dump.read_bytes()).hexdigest(),
            encrypted_size=dump.stat().st_size,
            alembic_head=base.db_dump.alembic_head,
            dumped_at=base.db_dump.dumped_at,
        ),
        snapshot=base.snapshot,
    )

    async def instant(_: float) -> None:
        return None

    run = await tg.publish_run(
        target,
        header=header,
        objects=[],
        dump_path=dump,
        source_keys=0,
        orphan_candidates=0,
        scratch_dir=scratch,
        sleep=instant,
        clock=lambda: datetime(2026, 10, 4, 12, 10, tzinfo=UTC),
    )
    assert sorted(client.objects) == [f"db/{RUN}/plan-estimate.sql.gz.age", f"runs/{RUN}/COMPLETE.json", f"runs/{RUN}/manifest.jsonl"]
    assert mf.verify_run(client.objects[run.complete_key], client.objects[run.manifest_key]).run_id == RUN
    puts = [call["key"] for name, call in client.calls if name == "put_object"]
    assert puts == [f"db/{RUN}/plan-estimate.sql.gz.age", f"runs/{RUN}/manifest.jsonl", f"runs/{RUN}/COMPLETE.json"]
    assert all(call["if_none_match"] == "*" for name, call in client.calls if name == "put_object")


# --- instance principal construction ------------------------------------------------------------------------


def fake_oci(signer_factory: Any, record: dict[str, Any]) -> types.ModuleType:
    module = types.ModuleType("oci")

    class Client:
        def __init__(self, config: dict[str, str], **kwargs: Any) -> None:
            record["config"], record["kwargs"] = config, kwargs

    module.auth = types.SimpleNamespace(  # type: ignore[attr-defined]
        signers=types.SimpleNamespace(InstancePrincipalsSecurityTokenSigner=signer_factory)
    )
    module.object_storage = types.SimpleNamespace(ObjectStorageClient=Client)  # type: ignore[attr-defined]
    module.retry = types.SimpleNamespace(NoneRetryStrategy=lambda: "no-retry")  # type: ignore[attr-defined]
    return module


def test_instance_principal_client_is_built_without_sdk_retries(monkeypatch):
    record: dict[str, Any] = {}
    signer = object()
    monkeypatch.setitem(sys.modules, "oci", fake_oci(lambda: signer, record))
    built = ot.OciBackupTarget.from_instance_principal(namespace=NS, bucket=BUCKET, region="eu-frankfurt-1")
    assert isinstance(built, ot.OciBackupTarget)
    assert record["config"] == {"region": "eu-frankfurt-1"}
    assert record["kwargs"] == {"signer": signer, "retry_strategy": "no-retry", "timeout": (10.0, 120.0)}


def test_missing_sdk_or_principal_is_a_configuration_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "oci", None)
    with pytest.raises(MediaStorageMisconfigured, match="oci==2.187.1"):
        ot.OciBackupTarget.from_instance_principal(namespace=NS, bucket=BUCKET)

    def no_principal() -> None:
        raise ConnectionRefusedError("169.254.169.254 refused")

    monkeypatch.setitem(sys.modules, "oci", fake_oci(no_principal, {}))
    with pytest.raises(MediaStorageMisconfigured, match="instance principal") as caught:
        ot.OciBackupTarget.from_instance_principal(namespace=NS, bucket=BUCKET)
    assert caught.value.error_code == "ConnectionRefusedError" and "169.254" not in str(caught.value)

