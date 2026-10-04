"""Stage 14D.4.6 OCI restore-principal smoke (operator tool, owner workstation).

Proves that the restore operator (IAM user in group plan-estimate-backup-restore,
policy plan-estimate-backup-restore-policy; docs/STAGE_14D3_ORACLE_BACKUP_PROVISIONING.md
§6.2 / §11, docs/STAGE_14D4_CONNECTIVITY_SEMANTICS_SMOKE.md §7) can READ both
backup buckets and can WRITE nothing:

  allowed   GetBucket (drill and production), list objects (drill and
            production), HEAD / GET / list versions of the 14D.4.5 probe object
  denied    PutObject of a new name, DeleteObject, multipart upload, bucket
            update -- all attempted against the DRILL bucket only
  invariant the probe object is unchanged (same size, exactly one version) and
            the attempted new name does not exist

Nothing is ever written to or deleted from the production bucket: only
GetBucket and ListObjects are issued there. Authentication is the owner's API
signing key from a local OCI config file (private key stays on the
workstation, never on the VM).

    python stage14d4_oci_restore_smoke.py --namespace <ns> \\
        --config ~/.oci-restore-proof/config \\
        --probe-object smoke/14d4/<utc>-<random>/probe.bin

Output: one line per check (name, expectation, observation, HTTP status / OCI
error code). Never printed: key material, OCIDs, fingerprints, namespace,
request ids, object contents, exception messages.

Exit codes: 0 all checks PASS, 1 at least one check FAIL, 2 cannot run.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

EXIT_PASS, EXIT_FAIL, EXIT_CANNOT_RUN = 0, 1, 2
OCI_SDK_PIN = "oci==2.187.1"
DEFAULT_REGION = "eu-frankfurt-1"
DEFAULT_DRILL_BUCKET = "plan-estimate-backup-drill"
DEFAULT_PROD_BUCKET = "plan-estimate-backup-prod"
PROBE_BYTES = 64 * 1024
WRITE_DENIED_PREFIX = "smoke/14d4/restore-write-denied-"
# OCI reports an authorization failure as 404 BucketNotFound / NotAuthorizedOrNotFound
# (or 401 / 403); a refused conditional write is 409 / 412.
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


def validate_probe_object(name: str) -> None:
    if not name.startswith("smoke/14d4/") or not name.endswith("/probe.bin") or ".." in name:
        raise ValueError("--probe-object must be the smoke/14d4/<utc>-<random>/probe.bin name printed by 14D.4.5")


def validate_buckets(drill: str, prod: str) -> None:
    if drill == prod:
        raise ValueError("drill and production bucket must differ")
    if "drill" not in drill:
        raise ValueError(f"refusing to attempt writes: bucket {drill!r} is not a drill bucket")
    if "drill" in prod:
        raise ValueError(f"production bucket {prod!r} looks like a drill bucket")


class RestoreSmoke:
    """Runs the checks with an injected ObjectStorageClient-like `client`."""

    def __init__(
        self,
        client: Any,
        namespace: str,
        drill_bucket: str,
        prod_bucket: str,
        probe_object: str,
        denied_write_name: str,
        update_bucket_details: Callable[[], Any],
        multipart_details: Callable[[str], Any],
        expected_size: int = PROBE_BYTES,
    ) -> None:
        validate_buckets(drill_bucket, prod_bucket)
        validate_probe_object(probe_object)
        if not denied_write_name.startswith(WRITE_DENIED_PREFIX):
            raise ValueError("denied write name must live under the restore-write-denied prefix")
        self.client = client
        self.ns = namespace
        self.drill = drill_bucket
        self.prod = prod_bucket
        self.probe = probe_object
        self.write_name = denied_write_name
        self.update_bucket_details = update_bucket_details
        self.multipart_details = multipart_details
        self.expected_size = expected_size
        self.results: list[CheckResult] = []

    def _expect(self, name: str, expect: str, result: Attempt, extra_ok: bool = True, note: str = "") -> Attempt:
        wanted = "allowed" if expect == "allow" else "denied"
        detail = result.detail + (f"; {note}" if note else "")
        self.results.append(CheckResult(name, expect, result.observed, detail, result.observed == wanted and extra_ok))
        return result

    def _invariant(self, name: str, holds: bool, detail: str) -> None:
        self.results.append(CheckResult(name, "invariant", "holds" if holds else "violated", detail, holds))

    def run(self) -> list[CheckResult]:
        self._expect(
            "restore_get_bucket[drill]", "allow", attempt(lambda: self.client.get_bucket(self.ns, self.drill))
        )
        self._expect("restore_get_bucket[prod]", "allow", attempt(lambda: self.client.get_bucket(self.ns, self.prod)))

        listed = attempt(
            lambda: [o.name for o in self.client.list_objects(self.ns, self.drill, prefix=self.probe).data.objects]
        )
        self._expect("restore_list_objects[drill]", "allow", listed, extra_ok=listed.value == [self.probe])
        self._expect(
            "restore_list_objects[prod]",
            "allow",
            attempt(lambda: self.client.list_objects(self.ns, self.prod, prefix="photos/", limit=1)),
        )

        head = attempt(lambda: self.client.head_object(self.ns, self.drill, self.probe))
        size = str(head.value.headers.get("content-length")) if head.observed == "allowed" else ""
        self._expect(
            "restore_head_probe",
            "allow",
            head,
            extra_ok=size == str(self.expected_size),
            note=f"content-length={size}",
        )
        got = attempt(lambda: len(body_bytes(self.client.get_object(self.ns, self.drill, self.probe).data)))
        self._expect(
            "restore_get_probe",
            "allow",
            got,
            extra_ok=got.value == self.expected_size,
            note=f"bytes={got.value}",
        )

        self._expect(
            "restore_put_new_object[drill]",
            "deny",
            attempt(lambda: self.client.put_object(self.ns, self.drill, self.write_name, b"restore-write-attempt")),
        )
        self._expect(
            "restore_delete_probe[drill]",
            "deny",
            attempt(lambda: self.client.delete_object(self.ns, self.drill, self.probe)),
        )
        multipart = attempt(
            lambda: self.client.create_multipart_upload(self.ns, self.drill, self.multipart_details(self.write_name))
        )
        note = ""
        if multipart.observed == "allowed":
            upload_id = getattr(multipart.value.data, "upload_id", None)
            aborted = attempt(lambda: self.client.abort_multipart_upload(self.ns, self.drill, self.write_name, upload_id))
            note = f"UNEXPECTED: multipart started; abort {aborted.observed}"
        self._expect("restore_multipart_upload[drill]", "deny", multipart, note=note)
        self._expect(
            "restore_update_bucket[drill]",
            "deny",
            attempt(lambda: self.client.update_bucket(self.ns, self.drill, self.update_bucket_details())),
        )

        self._state_invariants()
        return self.results

    def _state_invariants(self) -> None:
        versions = attempt(
            lambda: [
                v
                for v in (self.client.list_object_versions(self.ns, self.drill, prefix=self.probe).data.items or [])
                if v.name == self.probe
            ]
        )
        after = attempt(lambda: self.client.head_object(self.ns, self.drill, self.probe))
        size = after.value.headers.get("content-length") if after.observed == "allowed" else None
        live = (
            [v for v in versions.value if not getattr(v, "is_delete_marker", False)]
            if versions.observed == "allowed"
            else []
        )
        self._invariant(
            "restore_probe_unchanged",
            versions.observed == "allowed"
            and after.observed == "allowed"
            and str(size) == str(self.expected_size)
            and len(versions.value) == 1
            and len(live) == 1,
            f"content-length={size}; versions={len(versions.value) if versions.observed == 'allowed' else 'unreadable'}",
        )
        absent = attempt(
            lambda: [o.name for o in self.client.list_objects(self.ns, self.drill, prefix=self.write_name).data.objects]
        )
        self._invariant(
            "restore_denied_write_absent",
            absent.observed == "allowed" and absent.value == [],
            "no object under the attempted name" if absent.value == [] else absent.detail,
        )


def format_report(results: list[CheckResult]) -> str:
    lines = [f"{'check':36} {'expect':9} {'observed':9} result  detail"]
    for r in results:
        lines.append(f"{r.name:36} {r.expect:9} {r.observed:9} {'PASS' if r.passed else 'FAIL':6}  {r.detail}")
    failed = sum(not r.passed for r in results)
    lines.append("")
    lines.append(f"RESULT: {'PASS' if failed == 0 else 'FAIL'} ({len(results) - failed}/{len(results)} checks passed)")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--namespace", default=os.environ.get("OCI_NAMESPACE", ""), help="Object Storage namespace")
    parser.add_argument("--config", default=os.environ.get("OCI_CONFIG_FILE", ""), help="OCI config file path")
    parser.add_argument("--profile", default="DEFAULT")
    parser.add_argument("--probe-object", required=True, help="smoke/14d4/<utc>-<random>/probe.bin from 14D.4.5")
    parser.add_argument("--drill-bucket", default=DEFAULT_DRILL_BUCKET)
    parser.add_argument("--prod-bucket", default=DEFAULT_PROD_BUCKET)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        import oci  # type: ignore[import-not-found,unused-ignore]
    except ImportError:
        print(f"cannot run: the OCI SDK is not installed (pip install {OCI_SDK_PIN})", file=sys.stderr)
        return EXIT_CANNOT_RUN
    if not args.namespace or not args.config:
        print("cannot run: --namespace and --config (or OCI_NAMESPACE / OCI_CONFIG_FILE) are required", file=sys.stderr)
        return EXIT_CANNOT_RUN
    try:
        config = oci.config.from_file(os.path.expanduser(args.config), args.profile)
        config["region"] = DEFAULT_REGION
        client = oci.object_storage.ObjectStorageClient(config, retry_strategy=oci.retry.NoneRetryStrategy())
        models = oci.object_storage.models
        smoke = RestoreSmoke(
            client,
            args.namespace,
            args.drill_bucket,
            args.prod_bucket,
            args.probe_object,
            f"{WRITE_DENIED_PREFIX}{secrets.token_hex(4)}.bin",
            update_bucket_details=lambda: models.UpdateBucketDetails(versioning="Enabled"),
            multipart_details=lambda name: models.CreateMultipartUploadDetails(object=name),
        )
    except Exception as exc:  # noqa: BLE001 - configuration problems are reported by type only (no paths, no key data)
        print(f"cannot run: {type(exc).__name__} while loading the OCI config or arguments", file=sys.stderr)
        return EXIT_CANNOT_RUN
    results = smoke.run()
    if args.json:
        print(json.dumps({"checks": [asdict(r) for r in results]}, indent=2))
    else:
        print(format_report(results))
    return EXIT_PASS if all(r.passed for r in results) else EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
