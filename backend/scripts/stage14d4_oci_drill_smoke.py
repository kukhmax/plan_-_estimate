"""Stage 14D.4 OCI drill-bucket permission smoke (operator tool).

Proves, against the real Oracle Object Storage drill bucket and with the VM's
instance principal (dynamic group plan-estimate-backup-uploader-dg, Phase A
policy), what the future uploader can and cannot do
(docs/STAGE_14D3_ORACLE_BACKUP_PROVISIONING.md §6.2, §11;
docs/STAGE_14D4_CONNECTIVITY_SEMANTICS_SMOKE.md §5):

  allowed   GetBucket, PutObject of a NEW name, HEAD / GET / list / list versions
  denied    overwrite of an existing name (plain and If-None-Match: *), object
            delete, object-version delete, multipart upload, bucket update,
            any access to the production backup bucket
  invariant drill versioning enabled; the probe object is byte-identical and
            has exactly one version after every denied write

The probe object (smoke/14d4/<utc>-<random>/probe.bin, 64 KiB of random bytes)
stays in the drill bucket: the principal cannot delete, by design; drill
cleanup is a manual owner step. Nothing is written to the production bucket:
only GetBucket and ListObjects are attempted there.

Runs standalone (stdlib + the official `oci` SDK), e.g. in a disposable
python:3.12-slim container on the uploader network (br-pe-upload):

    python stage14d4_oci_drill_smoke.py --namespace <ns>
    python stage14d4_oci_drill_smoke.py --namespace <ns> --auth-only

`--auth-only` only tries to obtain the instance principal (IMDS) and makes no
Object Storage call: exit 0 = obtained, 3 = not obtainable (the expected result
from any container outside the uploader bridge once the IMDS guard is active).

Output: one line per check (name, expectation, observation, HTTP status / OCI
error code). Never printed: tokens, certificates, OCIDs, request ids, object
contents, exception messages.

Exit codes: 0 all checks PASS, 1 at least one check FAIL, 2 cannot run
(arguments, SDK missing), 3 instance principal not obtainable.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

EXIT_PASS, EXIT_FAIL, EXIT_CANNOT_RUN, EXIT_NO_PRINCIPAL = 0, 1, 2, 3
OCI_SDK_PIN = "oci==2.187.1"
DEFAULT_REGION = "eu-frankfurt-1"
DEFAULT_DRILL_BUCKET = "plan-estimate-backup-drill"
DEFAULT_PROD_BUCKET = "plan-estimate-backup-prod"
PROBE_BYTES = 64 * 1024
# OCI reports an authorization failure as 404 NotAuthorizedOrNotFound (or
# 401 / 403); a refused conditional write is 409 / 412.
DENIED_STATUSES = frozenset({401, 403, 404, 409, 412})


@dataclass(frozen=True)
class CheckResult:
    name: str
    expect: str  # allow | deny | invariant
    observed: str  # allowed | denied | error | skipped | holds | violated
    detail: str
    passed: bool


@dataclass(frozen=True)
class Attempt:
    observed: str  # allowed | denied | error
    value: Any = None
    status: int | None = None
    code: str = ""

    @property
    def detail(self) -> str:
        if self.observed == "allowed":
            return "ok"
        return f"HTTP {self.status} {self.code}".strip() if self.status is not None else self.code


def service_error_facts(exc: BaseException) -> tuple[int, str] | None:
    """(status, code) of an oci.exceptions.ServiceError (duck-typed)."""
    status, code = getattr(exc, "status", None), getattr(exc, "code", None)
    if isinstance(status, int) and isinstance(code, str):
        return status, code
    return None


def attempt(fn: Callable[[], Any]) -> Attempt:
    try:
        return Attempt("allowed", value=fn())
    except Exception as exc:  # noqa: BLE001 - a smoke check classifies every failure; only type/status/code are kept
        facts = service_error_facts(exc)
        if facts is None:
            return Attempt("error", code=type(exc).__name__)
        status, code = facts
        return Attempt("denied" if status in DENIED_STATUSES else "error", status=status, code=code)


def body_bytes(data: Any) -> bytes:
    """GetObject response body (requests.Response-like) as bytes."""
    content = getattr(data, "content", None)
    if isinstance(content, bytes):
        return content
    return bytes(data.read())


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def probe_object_name(now: datetime, token: str) -> str:
    return f"smoke/14d4/{now.strftime('%Y%m%dT%H%M%SZ')}-{token}/probe.bin"


def validate_buckets(drill: str, prod: str) -> None:
    if drill == prod:
        raise ValueError("drill and production bucket must differ")
    if "drill" not in drill:
        raise ValueError(f"refusing to write: bucket {drill!r} is not a drill bucket")
    if "drill" in prod:
        raise ValueError(f"production bucket {prod!r} looks like a drill bucket")


class DrillSmoke:
    """Runs the checks with an injected ObjectStorageClient-like `client`."""

    def __init__(
        self,
        client: Any,
        namespace: str,
        drill_bucket: str,
        prod_bucket: str,
        object_name: str,
        body: bytes,
        overwrite_body: bytes,
        update_bucket_details: Callable[[], Any],
        multipart_details: Callable[[str], Any],
    ) -> None:
        validate_buckets(drill_bucket, prod_bucket)
        if body == overwrite_body:
            raise ValueError("overwrite body must differ from the probe body")
        self.client = client
        self.ns = namespace
        self.drill = drill_bucket
        self.prod = prod_bucket
        self.name = object_name
        self.body = body
        self.overwrite_body = overwrite_body
        self.update_bucket_details = update_bucket_details
        self.multipart_details = multipart_details
        self.results: list[CheckResult] = []

    # -- recording helpers ---------------------------------------------------

    def _expect(self, name: str, expect: str, result: Attempt, extra_ok: bool = True, note: str = "") -> Attempt:
        wanted = "allowed" if expect == "allow" else "denied"
        detail = result.detail + (f"; {note}" if note else "")
        self.results.append(CheckResult(name, expect, result.observed, detail, result.observed == wanted and extra_ok))
        return result

    def _invariant(self, name: str, holds: bool, detail: str) -> None:
        self.results.append(CheckResult(name, "invariant", "holds" if holds else "violated", detail, holds))

    def _skip(self, name: str, expect: str, reason: str) -> None:
        self.results.append(CheckResult(name, expect, "skipped", reason, False))

    # -- probe-object facts ----------------------------------------------------

    def _versions(self) -> Attempt:
        def call() -> list[Any]:
            items = self.client.list_object_versions(self.ns, self.drill, prefix=self.name).data.items or []
            return [v for v in items if v.name == self.name]

        return attempt(call)

    def _content_sha(self) -> Attempt:
        return attempt(lambda: sha256_hex(body_bytes(self.client.get_object(self.ns, self.drill, self.name).data)))

    # -- checks ----------------------------------------------------------------

    def run(self) -> list[CheckResult]:
        bucket = self._expect("drill_get_bucket", "allow", attempt(lambda: self.client.get_bucket(self.ns, self.drill)))
        if bucket.observed == "allowed":
            versioning = getattr(bucket.value.data, "versioning", None)
            self._invariant("drill_versioning_enabled", versioning == "Enabled", f"versioning={versioning}")
        else:
            self._skip("drill_versioning_enabled", "invariant", "bucket not readable")

        md5 = base64.b64encode(hashlib.md5(self.body).digest()).decode()  # Content-MD5 integrity header, not a security hash
        created = self._expect(
            "drill_create_new_object",
            "allow",
            attempt(
                lambda: self.client.put_object(
                    self.ns,
                    self.drill,
                    self.name,
                    self.body,
                    if_none_match="*",
                    content_md5=md5,
                    content_length=len(self.body),
                    content_type="application/octet-stream",
                )
            ),
        )
        object_checks = (
            ("drill_head_object", "allow"),
            ("drill_get_object", "allow"),
            ("drill_list_objects", "allow"),
            ("drill_list_object_versions", "allow"),
            ("drill_overwrite_existing", "deny"),
            ("drill_conditional_create_existing", "deny"),
            ("drill_delete_object", "deny"),
            ("drill_delete_object_version", "deny"),
            ("drill_object_unchanged", "invariant"),
        )
        if created.observed != "allowed":
            for name, expect in object_checks:
                self._skip(name, expect, "probe object was not created")
        else:
            self._object_checks()

        self._multipart_check()
        self._expect(
            "drill_update_bucket",
            "deny",
            attempt(lambda: self.client.update_bucket(self.ns, self.drill, self.update_bucket_details())),
        )
        self._expect("prod_get_bucket", "deny", attempt(lambda: self.client.get_bucket(self.ns, self.prod)))
        self._expect(
            "prod_list_objects",
            "deny",
            attempt(lambda: self.client.list_objects(self.ns, self.prod, prefix="smoke/", limit=1)),
            note="OCI reports NotAuthorizedOrNotFound for both a denial and a missing bucket",
        )
        return self.results

    def _object_checks(self) -> None:
        head = attempt(lambda: self.client.head_object(self.ns, self.drill, self.name))
        size = str(head.value.headers.get("content-length")) if head.observed == "allowed" else ""
        self._expect(
            "drill_head_object", "allow", head, extra_ok=size == str(len(self.body)), note=f"content-length={size}"
        )

        original_sha = sha256_hex(self.body)
        content = self._content_sha()
        self._expect("drill_get_object", "allow", content, extra_ok=content.value == original_sha, note="sha256 match")

        listed = attempt(
            lambda: [o.name for o in self.client.list_objects(self.ns, self.drill, prefix=self.name).data.objects]
        )
        self._expect("drill_list_objects", "allow", listed, extra_ok=listed.value == [self.name])

        versions = self._versions()
        count = len(versions.value) if versions.observed == "allowed" else -1
        self._expect("drill_list_object_versions", "allow", versions, extra_ok=count == 1, note=f"versions={count}")
        version_id = versions.value[0].version_id if count == 1 else None

        self._expect(
            "drill_overwrite_existing",
            "deny",
            attempt(lambda: self.client.put_object(self.ns, self.drill, self.name, self.overwrite_body)),
        )
        self._expect(
            "drill_conditional_create_existing",
            "deny",
            attempt(
                lambda: self.client.put_object(
                    self.ns, self.drill, self.name, self.overwrite_body, if_none_match="*"
                )
            ),
        )
        self._expect(
            "drill_delete_object", "deny", attempt(lambda: self.client.delete_object(self.ns, self.drill, self.name))
        )
        if version_id is None:
            self._skip("drill_delete_object_version", "deny", "no single version id to target")
        else:
            self._expect(
                "drill_delete_object_version",
                "deny",
                attempt(lambda: self.client.delete_object(self.ns, self.drill, self.name, version_id=version_id)),
            )

        after_sha = self._content_sha()
        after_versions = self._versions()
        live = (
            [v for v in after_versions.value if not getattr(v, "is_delete_marker", False)]
            if after_versions.observed == "allowed"
            else []
        )
        holds = (
            after_sha.value == original_sha
            and after_versions.observed == "allowed"
            and len(after_versions.value) == 1
            and len(live) == 1
        )
        self._invariant(
            "drill_object_unchanged",
            holds,
            f"sha256 {'match' if after_sha.value == original_sha else 'MISMATCH'}; "
            f"versions={len(after_versions.value) if after_versions.observed == 'allowed' else 'unreadable'}",
        )

    def _multipart_check(self) -> None:
        name = f"{self.name}.multipart"
        result = attempt(lambda: self.client.create_multipart_upload(self.ns, self.drill, self.multipart_details(name)))
        note = ""
        if result.observed == "allowed":
            upload_id = getattr(result.value.data, "upload_id", None)
            aborted = attempt(lambda: self.client.abort_multipart_upload(self.ns, self.drill, name, upload_id))
            note = f"UNEXPECTED: multipart started; abort {aborted.observed}"
        self._expect("drill_multipart_upload", "deny", result, note=note)


def format_report(results: list[CheckResult], object_name: str) -> str:
    lines = [f"{'check':36} {'expect':9} {'observed':9} result  detail"]
    for r in results:
        lines.append(f"{r.name:36} {r.expect:9} {r.observed:9} {'PASS' if r.passed else 'FAIL':6}  {r.detail}")
    failed = sum(not r.passed for r in results)
    lines.append("")
    lines.append(f"probe object left in the drill bucket: {object_name}")
    lines.append(f"RESULT: {'PASS' if failed == 0 else 'FAIL'} ({len(results) - failed}/{len(results)} checks passed)")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--namespace", default=os.environ.get("OCI_NAMESPACE", ""), help="Object Storage namespace")
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--drill-bucket", default=DEFAULT_DRILL_BUCKET)
    parser.add_argument("--prod-bucket", default=DEFAULT_PROD_BUCKET)
    parser.add_argument("--auth-only", action="store_true", help="only obtain the instance principal, no API call")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        import oci  # type: ignore[import-not-found,unused-ignore]
    except ImportError:
        print(f"cannot run: the OCI SDK is not installed (pip install {OCI_SDK_PIN})", file=sys.stderr)
        return EXIT_CANNOT_RUN

    try:
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    except Exception as exc:  # noqa: BLE001 - any failure means: no instance principal from here
        print(f"instance principal: NOT obtainable ({type(exc).__name__})")
        return EXIT_NO_PRINCIPAL
    print("instance principal: obtained")
    if args.auth_only:
        return EXIT_PASS

    if not args.namespace:
        print("cannot run: --namespace (or OCI_NAMESPACE) is required", file=sys.stderr)
        return EXIT_CANNOT_RUN
    now = datetime.now(UTC)
    object_name = probe_object_name(now, secrets.token_hex(4))
    client = oci.object_storage.ObjectStorageClient(
        {"region": args.region}, signer=signer, retry_strategy=oci.retry.NoneRetryStrategy()
    )
    models = oci.object_storage.models
    try:
        smoke = DrillSmoke(
            client,
            args.namespace,
            args.drill_bucket,
            args.prod_bucket,
            object_name,
            secrets.token_bytes(PROBE_BYTES),
            secrets.token_bytes(PROBE_BYTES),
            update_bucket_details=lambda: models.UpdateBucketDetails(versioning="Enabled"),
            multipart_details=lambda name: models.CreateMultipartUploadDetails(object=name),
        )
    except ValueError as exc:
        print(f"cannot run: {exc}", file=sys.stderr)
        return EXIT_CANNOT_RUN
    results = smoke.run()
    if args.json:
        print(json.dumps({"object": object_name, "checks": [asdict(r) for r in results]}, indent=2))
    else:
        print(format_report(results, object_name))
    return EXIT_PASS if all(r.passed for r in results) else EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
