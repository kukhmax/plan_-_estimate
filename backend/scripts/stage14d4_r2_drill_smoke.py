"""Stage 14D.4 Cloudflare R2 drill-token smoke (operator tool).

Proves that one R2 drill token (Object Read & Write, scoped to one drill
bucket; docs/STAGE_14D4_CONNECTIVITY_SEMANTICS_SMOKE.md §6) works on its own
bucket and nowhere else:

  allowed   PutObject of a new key (If-None-Match: *), HEAD, GET, list,
            delete of the smoke object (cleanup; R2 object tokens cannot
            exclude delete, which is why drill tokens never see production)
  denied    a second conditional PutObject on the same key (HTTP 412);
            list / HeadBucket on every bucket in R2_FORBIDDEN_BUCKETS
            (HTTP 401 / 403; nothing is ever written there)
  invariant the object is byte-identical after the refused write; it is gone
            after cleanup

Configuration comes only from the environment (an env file passed with
`docker run --env-file`, chmod 600, outside the repository):

    R2_ENDPOINT_URL        https://<account-id>.eu.r2.cloudflarestorage.com (EU jurisdiction)
    R2_ACCESS_KEY_ID       drill token access key id
    R2_SECRET_ACCESS_KEY   drill token secret
    R2_BUCKET              the token's own drill bucket (name must contain "drill")
    R2_FORBIDDEN_BUCKETS   comma-separated buckets the token must not reach

Runs standalone (stdlib + boto3), e.g. in a disposable python:3.12-slim
container. Never printed: credentials, the endpoint / account id, object
contents, provider error messages.

Exit codes: 0 all checks PASS, 1 at least one check FAIL, 2 cannot run.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import sys
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Any

EXIT_PASS, EXIT_FAIL, EXIT_CANNOT_RUN = 0, 1, 2
PROBE_BYTES = 64 * 1024
EU_ENDPOINT = re.compile(r"^https://[0-9a-f]{32}\.eu\.r2\.cloudflarestorage\.com/?$")
BUCKET_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")


@dataclass(frozen=True)
class CheckResult:
    name: str
    expect: str  # allow | deny | invariant
    observed: str  # allowed | denied | error | skipped | holds | violated
    detail: str
    passed: bool


@dataclass(frozen=True)
class Attempt:
    observed: str  # allowed | refused | error
    value: Any = None
    status: int | None = None
    code: str = ""

    @property
    def detail(self) -> str:
        if self.observed == "allowed":
            return "ok"
        return f"HTTP {self.status} {self.code}".strip() if self.status is not None else self.code


@dataclass(frozen=True)
class SmokeConfig:
    endpoint_url: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    forbidden_buckets: tuple[str, ...]

    def __repr__(self) -> str:  # never expose credentials or the account id
        return f"SmokeConfig(bucket={self.bucket!r}, forbidden_buckets={self.forbidden_buckets!r})"


def load_config(env: Mapping[str, str]) -> SmokeConfig:
    """Validate the environment; raises ValueError naming the variable only."""
    endpoint = env.get("R2_ENDPOINT_URL", "").strip()
    key_id = env.get("R2_ACCESS_KEY_ID", "").strip()
    secret = env.get("R2_SECRET_ACCESS_KEY", "").strip()
    bucket = env.get("R2_BUCKET", "").strip()
    forbidden = tuple(b.strip() for b in env.get("R2_FORBIDDEN_BUCKETS", "").split(",") if b.strip())
    if not EU_ENDPOINT.match(endpoint):
        raise ValueError("R2_ENDPOINT_URL must be the EU-jurisdiction https endpoint")
    if not key_id or not secret:
        raise ValueError("R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY are required")
    for name in (bucket, *forbidden):
        if not BUCKET_NAME.match(name):
            raise ValueError(f"invalid bucket name {name!r}")
    if "drill" not in bucket:
        raise ValueError(f"refusing to write: R2_BUCKET {bucket!r} is not a drill bucket")
    if not forbidden:
        raise ValueError("R2_FORBIDDEN_BUCKETS must name at least one bucket the token must not reach")
    if bucket in forbidden:
        raise ValueError("R2_BUCKET must not be listed in R2_FORBIDDEN_BUCKETS")
    return SmokeConfig(endpoint, key_id, secret, bucket, forbidden)


def client_error_facts(exc: BaseException) -> tuple[int | None, str] | None:
    """(HTTP status, error code) of a botocore ClientError (duck-typed)."""
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    error = response.get("Error") or {}
    meta = response.get("ResponseMetadata") or {}
    return meta.get("HTTPStatusCode"), str(error.get("Code", ""))


def attempt(fn: Callable[[], Any], refused_statuses: frozenset[int]) -> Attempt:
    try:
        return Attempt("allowed", value=fn())
    except Exception as exc:  # noqa: BLE001 - a smoke check classifies every failure; only type/status/code are kept
        facts = client_error_facts(exc)
        if facts is None:
            return Attempt("error", code=type(exc).__name__)
        status, code = facts
        return Attempt("refused" if status in refused_statuses else "error", status=status, code=code)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def probe_key(now: datetime, token: str) -> str:
    return f"smoke/14d4/{now.strftime('%Y%m%dT%H%M%SZ')}-{token}/probe.bin"


NO_REFUSAL: frozenset[int] = frozenset()
ACCESS_DENIED = frozenset({401, 403})
PRECONDITION_FAILED = frozenset({412})


class R2DrillSmoke:
    def __init__(self, client: Any, bucket: str, forbidden: tuple[str, ...], key: str, body: bytes) -> None:
        self.client, self.bucket, self.forbidden, self.key, self.body = client, bucket, forbidden, key, body
        self.results: list[CheckResult] = []

    def _record(self, name: str, expect: str, result: Attempt, extra_ok: bool = True, note: str = "") -> Attempt:
        wanted = "allowed" if expect == "allow" else "refused"
        observed = "denied" if result.observed == "refused" else result.observed
        detail = result.detail + (f"; {note}" if note else "")
        self.results.append(CheckResult(name, expect, observed, detail, result.observed == wanted and extra_ok))
        return result

    def _invariant(self, name: str, holds: bool, detail: str) -> None:
        self.results.append(CheckResult(name, "invariant", "holds" if holds else "violated", detail, holds))

    def _get_sha(self) -> Attempt:
        return attempt(
            lambda: sha256_hex(self.client.get_object(Bucket=self.bucket, Key=self.key)["Body"].read()), NO_REFUSAL
        )

    def run(self) -> list[CheckResult]:
        md5 = base64.b64encode(hashlib.md5(self.body).digest()).decode()  # Content-MD5 integrity header, not a security hash
        created = self._record(
            "r2_create_new_object",
            "allow",
            attempt(
                lambda: self.client.put_object(
                    Bucket=self.bucket,
                    Key=self.key,
                    Body=self.body,
                    IfNoneMatch="*",
                    ContentMD5=md5,
                    ContentLength=len(self.body),
                    ContentType="application/octet-stream",
                ),
                NO_REFUSAL,
            ),
        )
        if created.observed == "allowed":
            self._object_checks()
        else:
            for name, expect in (
                ("r2_head_object", "allow"),
                ("r2_get_object", "allow"),
                ("r2_list_objects", "allow"),
                ("r2_conditional_create_existing", "deny"),
                ("r2_object_unchanged", "invariant"),
                ("r2_cleanup_delete", "allow"),
                ("r2_cleanup_verified", "invariant"),
            ):
                self.results.append(CheckResult(name, expect, "skipped", "probe object was not created", False))
        for other in self.forbidden:
            self._record(
                f"r2_forbidden_list[{other}]",
                "deny",
                attempt(partial(self.client.list_objects_v2, Bucket=other, MaxKeys=1), ACCESS_DENIED),
            )
            self._record(
                f"r2_forbidden_head_bucket[{other}]",
                "deny",
                attempt(partial(self.client.head_bucket, Bucket=other), ACCESS_DENIED),
            )
        return self.results

    def _object_checks(self) -> None:
        head = attempt(lambda: self.client.head_object(Bucket=self.bucket, Key=self.key), NO_REFUSAL)
        size = head.value.get("ContentLength") if head.observed == "allowed" else None
        self._record("r2_head_object", "allow", head, extra_ok=size == len(self.body), note=f"content-length={size}")

        original = sha256_hex(self.body)
        content = self._get_sha()
        self._record("r2_get_object", "allow", content, extra_ok=content.value == original, note="sha256 match")

        listed = attempt(
            lambda: [o["Key"] for o in self.client.list_objects_v2(Bucket=self.bucket, Prefix=self.key).get("Contents", [])],
            NO_REFUSAL,
        )
        self._record("r2_list_objects", "allow", listed, extra_ok=listed.value == [self.key])

        self._record(
            "r2_conditional_create_existing",
            "deny",
            attempt(
                lambda: self.client.put_object(
                    Bucket=self.bucket, Key=self.key, Body=b"overwrite-attempt", IfNoneMatch="*"
                ),
                PRECONDITION_FAILED,
            ),
        )
        after = self._get_sha()
        self._invariant(
            "r2_object_unchanged", after.value == original, f"sha256 {'match' if after.value == original else 'MISMATCH'}"
        )

        deleted = self._record(
            "r2_cleanup_delete",
            "allow",
            attempt(lambda: self.client.delete_object(Bucket=self.bucket, Key=self.key), NO_REFUSAL),
        )
        gone = attempt(lambda: self.client.head_object(Bucket=self.bucket, Key=self.key), frozenset({404}))
        self._invariant(
            "r2_cleanup_verified",
            deleted.observed == "allowed" and gone.observed == "refused",
            "object absent" if gone.observed == "refused" else f"head {gone.detail}",
        )


def format_report(results: list[CheckResult], bucket: str, key: str) -> str:
    lines = [f"bucket: {bucket}", f"{'check':52} {'expect':9} {'observed':9} result  detail"]
    for r in results:
        lines.append(f"{r.name:52} {r.expect:9} {r.observed:9} {'PASS' if r.passed else 'FAIL':6}  {r.detail}")
    failed = sum(not r.passed for r in results)
    lines.append("")
    lines.append(f"probe key (deleted by the cleanup check): {key}")
    lines.append(f"RESULT: {'PASS' if failed == 0 else 'FAIL'} ({len(results) - failed}/{len(results)} checks passed)")
    return "\n".join(lines)


def build_client(config: SmokeConfig) -> Any:
    import boto3
    from botocore.config import Config

    return boto3.session.Session().client(
        "s3",
        endpoint_url=config.endpoint_url,
        region_name="auto",
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        config=Config(
            signature_version="s3v4",
            connect_timeout=10,
            read_timeout=30,
            retries={"max_attempts": 1, "mode": "standard"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            s3={"addressing_style": "path"},
        ),
    )


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in args
    if any(a not in ("--json",) for a in args):
        print("usage: stage14d4_r2_drill_smoke.py [--json]  (configuration via environment, see docstring)")
        return EXIT_CANNOT_RUN
    try:
        config = load_config(os.environ if env is None else env)
    except ValueError as exc:
        print(f"cannot run: {exc}", file=sys.stderr)
        return EXIT_CANNOT_RUN
    try:
        client = build_client(config)
    except ImportError:
        print("cannot run: boto3 is not installed", file=sys.stderr)
        return EXIT_CANNOT_RUN
    key = probe_key(datetime.now(UTC), secrets.token_hex(4))
    results = R2DrillSmoke(client, config.bucket, config.forbidden_buckets, key, secrets.token_bytes(PROBE_BYTES)).run()
    if as_json:
        print(json.dumps({"bucket": config.bucket, "key": key, "checks": [asdict(r) for r in results]}, indent=2))
    else:
        print(format_report(results, config.bucket, key))
    return EXIT_PASS if all(r.passed for r in results) else EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
