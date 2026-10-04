"""Stage 14D.2I.3 media-restore live smoke (operator tool; DRILL buckets only).

Runs the production restore path -- `OciBackupReader` (backup bucket, read only) -> `restore_media` ->
`S3MediaStorage` (R2 drill-restore bucket) -- for a run that an earlier drill (the 14D.2G smoke) published in the Oracle
drill bucket (docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §16.15). Its objects are synthetic. The database half of the restore
needs a real encrypted dump and is proved by the 14D.5 drill; here the READY set is derived from the manifest itself, which
is what a smoke on synthetic data can do (the manifest <-> database association is covered by the automated tests and the
real-tool proof).

  1  restore_all_objects                 every object of the run restored and verified
  2  destination_matches_manifest        independent check: exactly the manifest's keys, sizes and SHA-256 values
  3  rerun_is_idempotent                 everything already present: no backup read, no write
  4  conflict_is_reported_and_kept       other bytes under a manifest key: reported for that object alone, untouched
  5  foreign_object_stops_restore        an object that is not part of the run: nothing is written
  6  unsafe_destination_refused          a forbidden bucket name: nothing is read or written
  7  damaged_backup_bytes_not_written    bytes changed in transit: reported, never written, the rest restored
  8  report_is_secret_free

The destination bucket must hold no object under photos/v1/ when the smoke starts (it then removes exactly what it
created; it never deletes anything else). Configuration (an env file passed with `docker run --env-file`, chmod 600,
outside the repository; the drill-RESTORE token):

    R2_ENDPOINT_URL        https://<account-id>.eu.r2.cloudflarestorage.com (EU jurisdiction)
    R2_ACCESS_KEY_ID       drill-restore token access key id (Object Read & Write on the drill-restore bucket)
    R2_SECRET_ACCESS_KEY   drill-restore token secret
    R2_BUCKET              the drill RESTORE bucket (name must contain "drill")
    R2_FORBIDDEN_BUCKETS   comma-separated buckets that must never be a destination (production, drill source)
    OCI_NAMESPACE          Object Storage namespace (or --namespace)

    python stage14d2i3_media_restore_smoke.py --namespace <ns> --run-id <run_id> [--oci-config FILE [--profile P]]

By default the backup bucket is read with the VM's instance principal; `--oci-config` selects an API-key config file
(the restore principal on the operator's workstation) instead. Never printed: credentials, endpoint, namespace, keys,
hashes, object contents, provider messages. Exit codes: 0 all PASS, 1 a check failed, 2 cannot run, 3 no OCI principal.
"""

import argparse
import asyncio
import hashlib
import os
import re
import secrets
import sys
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.backup import manifest as mf
from app.backup import media_sync as ms
from app.backup import restore_media as rm
from app.backup import target as tg
from app.backup.run_id import validate_run_id
from app.domain.exceptions import MediaStorageError
from app.domain.photos.keys import PHOTO_KEY_PREFIX
from app.domain.services.media_storage import MediaStorageAdmin, ObjectInfo

EXIT_PASS, EXIT_FAIL, EXIT_CANNOT_RUN, EXIT_NO_PRINCIPAL = 0, 1, 2, 3
DEFAULT_DRILL_BUCKET = "plan-estimate-backup-drill"
EU_ENDPOINT = re.compile(r"^https://[0-9a-f]{32}\.eu\.r2\.cloudflarestorage\.com/?$")
BUCKET_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
NO_RETRY = tg.RetryPolicy(max_attempts=1, base_delay=0.0)


class SmokeCannotRun(RuntimeError):
    """The smoke cannot start safely (for example the destination is not empty). The message names no value."""


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _describe(exc: BaseException) -> str:
    if isinstance(exc, MediaStorageError):
        return f"{type(exc).__name__} (code={exc.error_code}, status={exc.http_status})"
    return type(exc).__name__


class Recorder:
    def __init__(self) -> None:
        self.results: list[CheckResult] = []

    async def check(self, name: str, step: Callable[[], Awaitable[str]]) -> bool:
        try:
            detail = await step()
        except Exception as exc:  # noqa: BLE001 - a check failure is reported as FAIL with the exception type, never swallowed
            self.results.append(CheckResult(name, False, _describe(exc)))
            return False
        self.results.append(CheckResult(name, True, detail))
        return True


class DestinationAdmin(Protocol):
    """What the smoke may do to its own drill bucket besides restoring: plant and remove objects."""

    async def put_bytes(self, key: str, data: bytes) -> None: ...

    async def delete(self, key: str) -> None: ...


# --- counting / fault-injecting wrappers ---------------------------------------------------------------------------------------


class Reader:
    """The backup bucket through `head` / `download_to` only, counting reads and optionally damaging one download."""

    def __init__(self, inner: tg.BackupReader, *, flip_download: str | None = None) -> None:
        self._inner = inner
        self._flip = flip_download
        self.downloads = 0

    async def head(self, key: str) -> tg.TargetObject | None:
        return await self._inner.head(key)

    async def download_to(self, key: str, path: Path) -> None:
        self.downloads += 1
        await self._inner.download_to(key, path)
        if key == self._flip:
            data = bytearray(path.read_bytes())
            data[0] ^= 0xFF
            path.write_bytes(bytes(data))


class Destination:
    """The destination store, counting what the restore does to it."""

    def __init__(self, inner: MediaStorageAdmin) -> None:
        self.inner = inner
        self.puts = 0
        self.calls = 0

    async def put_object(self, key: str, source: Path, content_type: str) -> None:
        self.puts += 1
        self.calls += 1
        await self.inner.put_object(key, source, content_type)

    async def head_object(self, key: str) -> ObjectInfo | None:
        self.calls += 1
        return await self.inner.head_object(key)

    async def presign_get(self, key: str, ttl_seconds: int) -> str:
        return await self.inner.presign_get(key, ttl_seconds)

    async def download_to(self, key: str, path: Path) -> None:
        self.calls += 1
        await self.inner.download_to(key, path)

    def iter_keys(self, prefix: str) -> AsyncIterator[str]:
        self.calls += 1
        return self.inner.iter_keys(prefix)


# --- the checks -----------------------------------------------------------------------------------------------------------------


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _list(destination: MediaStorageAdmin) -> set[str]:
    return {key async for key in destination.iter_keys(PHOTO_KEY_PREFIX)}


async def _read(destination: MediaStorageAdmin, key: str, scratch: Path) -> bytes:
    workdir = Path(tempfile.mkdtemp(prefix="read-", dir=scratch))
    try:
        path = workdir / "object"
        await destination.download_to(key, path)
        return path.read_bytes()
    finally:
        for child in workdir.iterdir():
            child.unlink()
        workdir.rmdir()


async def run_checks(
    backup: tg.BackupReader,
    destination: MediaStorageAdmin,
    admin: DestinationAdmin,
    scratch: Path,
    *,
    run_id: str,
    destination_bucket: str,
    forbidden_buckets: tuple[str, ...],
    created: set[str],
    retry: tg.RetryPolicy = tg.DEFAULT_RETRY,
) -> list[CheckResult]:
    """`created` receives every key the smoke put into the destination (also if a later step raises), for cleanup."""
    run = await ms.load_prior_run(backup, run_id, scratch_dir=scratch, retry=retry)
    objects = run.manifest.objects
    if len(objects) < 3 or not forbidden_buckets:
        raise SmokeCannotRun("the drill run needs at least three objects and a forbidden-bucket list")
    keys = {obj.key for obj in objects}
    if await _list(destination):
        raise SmokeCannotRun("the destination bucket must hold no object under photos/v1/ when the smoke starts")
    ready_assets = mf.ready_assets_from_objects(objects)
    rec = Recorder()
    counting = Destination(destination)

    async def restore(
        reader: tg.BackupReader | None = None, store: MediaStorageAdmin | None = None, bucket: str | None = None
    ) -> rm.MediaRestoreReport:
        try:
            return await rm.restore_media(
                backup if reader is None else reader,
                run,
                counting if store is None else store,
                destination_bucket=destination_bucket if bucket is None else bucket,
                forbidden_buckets=forbidden_buckets,
                ready_assets=ready_assets,
                scratch_dir=scratch,
                retry=retry,
            )
        finally:
            created.update(await _list(destination))

    async def restore_all() -> str:
        report = await restore()
        if not report.ok or report.counts.restored != len(objects):
            raise AssertionError("expected every object restored")
        return f"{report.counts.restored} objects restored ({report.counts.bytes_restored} bytes), each verified by re-download"

    async def matches_manifest() -> str:
        if await _list(destination) != keys:
            raise AssertionError("the destination does not hold exactly the manifest's keys")
        for obj in objects:
            facts = await destination.head_object(obj.key)
            data = await _read(destination, obj.key, scratch)
            if facts is None or facts.size != obj.size or len(data) != obj.size or _sha(data) != obj.sha256:
                raise AssertionError("an object differs from the manifest")
        return f"{len(objects)} objects: keys, sizes and SHA-256 equal the manifest"

    async def idempotent() -> str:
        reader = Reader(backup)
        counting.puts = 0
        report = await restore(reader=reader)
        if not report.ok or report.counts.already_present != len(objects) or report.counts.restored != 0:
            raise AssertionError("expected everything already present")
        if reader.downloads != 0 or counting.puts != 0:
            raise AssertionError("a resumed run must not read the backup or write")
        return f"{report.counts.already_present} already present; 0 backup reads, 0 writes"

    async def conflict() -> str:
        victim = objects[0]
        original = await _read(destination, victim.key, scratch)
        planted = bytes([original[0] ^ 0xFF]) + original[1:]
        await admin.delete(victim.key)
        await admin.put_bytes(victim.key, planted)
        report = await restore()
        expected = (rm.ObjectProblem(victim.asset_id, victim.role, rm.ObjectProblemCode.DESTINATION_CONFLICT),)
        if report.object_problems != expected or report.ok or report.counts.already_present != len(objects) - 1:
            raise AssertionError("expected exactly the conflict, everything else present")
        if await _read(destination, victim.key, scratch) != planted:
            raise AssertionError("the conflicting object was changed")
        await admin.delete(victim.key)
        return "DESTINATION_CONFLICT for the one object; its bytes were not touched"

    async def foreign() -> str:
        key = f"{PHOTO_KEY_PREFIX}00000000-0000-4000-8000-{secrets.token_hex(6)}/original.jpg"
        await admin.put_bytes(key, secrets.token_bytes(64))
        counting.puts = 0
        report = await restore()  # (its `finally` records the planted key for the final cleanup, whatever happens)
        await admin.delete(key)
        if report.preflight is not rm.Preflight.FOREIGN_OBJECTS_PRESENT or counting.puts != 0 or report.counts.foreign_objects != 1:
            raise AssertionError("an object outside the run must stop the restore before any write")
        return "FOREIGN_OBJECTS_PRESENT; nothing written"

    async def unsafe() -> str:
        before = counting.calls
        reader = Reader(backup)
        report = await restore(reader=reader, bucket=forbidden_buckets[0])
        if report.preflight is not rm.Preflight.DESTINATION_UNSAFE or counting.calls != before or reader.downloads != 0:
            raise AssertionError("a forbidden destination must be refused before anything is read or written")
        return "DESTINATION_UNSAFE; nothing read, nothing written"

    async def damaged() -> str:
        for key in sorted(await _list(destination)):
            await admin.delete(key)
        victim = objects[1]
        report = await restore(reader=Reader(backup, flip_download=victim.key))
        expected = (rm.ObjectProblem(victim.asset_id, victim.role, rm.ObjectProblemCode.BACKUP_SHA_MISMATCH),)
        if report.object_problems != expected or report.counts.restored != len(objects) - 1:
            raise AssertionError("expected exactly the damaged object reported and the rest restored")
        if victim.key in await _list(destination):
            raise AssertionError("a damaged object was written")
        return "BACKUP_SHA_MISMATCH for the one object; it was not written, the rest restored"

    async def secret_free() -> str:
        report = await restore()
        text = report.report_bytes().decode()
        leaks = [PHOTO_KEY_PREFIX in text, destination_bucket in text, *(obj.sha256 in text for obj in objects)]
        if any(leaks):
            raise AssertionError("the report leaks object names, hashes or a bucket name")
        return "report lists codes, asset ids and roles only"

    steps: list[tuple[str, Callable[[], Awaitable[str]]]] = [
        ("restore_all_objects", restore_all),
        ("destination_matches_manifest", matches_manifest),
        ("rerun_is_idempotent", idempotent),
        ("conflict_is_reported_and_kept", conflict),
        ("foreign_object_stops_restore", foreign),
        ("unsafe_destination_refused", unsafe),
        ("damaged_backup_bytes_not_written", damaged),
        ("report_is_secret_free", secret_free),
    ]
    stopped = False  # the steps build on the state the previous ones left
    for name, step in steps:
        if stopped:
            rec.results.append(CheckResult(name, False, "skipped: an earlier check failed"))
        elif not await rec.check(name, step):
            stopped = True
    return rec.results


def format_report(results: list[CheckResult], run_id: str) -> str:
    lines = [f"{'check':40} result  detail"]
    lines.extend(f"{r.name:40} {'PASS' if r.passed else 'FAIL':6}  {r.detail}" for r in results)
    failed = sum(not r.passed for r in results)
    lines += ["", f"restored run (the synthetic objects in the drill-restore bucket are removed afterwards): {run_id}"]
    lines.append(f"RESULT: {'PASS' if failed == 0 else 'FAIL'} ({len(results) - failed}/{len(results)} checks passed)")
    return "\n".join(lines)


# --- configuration and entry point ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class R2Config:
    endpoint_url: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    forbidden_buckets: tuple[str, ...]

    def __repr__(self) -> str:  # never expose credentials or the account id
        return f"R2Config(bucket={self.bucket!r})"


def load_r2_config(env: Mapping[str, str]) -> R2Config:
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
            raise ValueError("R2_BUCKET and R2_FORBIDDEN_BUCKETS must be valid bucket names")
    if "drill" not in bucket:
        raise ValueError("refusing to run: R2_BUCKET is not a drill bucket")
    if not forbidden:
        raise ValueError("R2_FORBIDDEN_BUCKETS must name at least one bucket that must never be a destination")
    if bucket in forbidden:
        raise ValueError("R2_BUCKET must not be listed in R2_FORBIDDEN_BUCKETS")
    return R2Config(endpoint, key_id, secret, bucket, forbidden)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--namespace", default=os.environ.get("OCI_NAMESPACE", ""), help="Object Storage namespace")
    parser.add_argument("--bucket", default=DEFAULT_DRILL_BUCKET, help="Oracle drill backup bucket")
    parser.add_argument("--region", default="eu-frankfurt-1")
    parser.add_argument("--run-id", required=True, help="a published drill run (see the 14D.2G smoke)")
    parser.add_argument("--oci-config", default=None, help="API-key config file (restore principal) instead of the instance principal")
    parser.add_argument("--profile", default="DEFAULT")
    return parser


def _cannot_run(message: str) -> int:
    print(f"cannot run: {message}", file=sys.stderr)
    return EXIT_CANNOT_RUN


async def amain(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    if "drill" not in args.bucket:
        return _cannot_run(f"refusing to read bucket {args.bucket!r} (not a drill bucket)")
    if not args.namespace:
        return _cannot_run("--namespace (or OCI_NAMESPACE) is required")
    try:
        validate_run_id(args.run_id)
        config = load_r2_config(env)
    except ValueError as exc:
        return _cannot_run(str(exc))
    try:
        import boto3
        from botocore.config import Config

        from app.backup.oci_target import OciBackupReader
        from app.core.s3_media_storage import S3MediaStorage
    except ImportError as exc:
        return _cannot_run(f"a required library is not installed ({type(exc).__name__})")

    try:
        if args.oci_config:
            reader = OciBackupReader.from_api_key_config(
                namespace=args.namespace, bucket=args.bucket, config_file=Path(args.oci_config), profile=args.profile,
                region=args.region,
            )  # fmt: skip
        else:
            reader = OciBackupReader.from_instance_principal(namespace=args.namespace, bucket=args.bucket, region=args.region)
    except MediaStorageError as exc:
        if exc.error_code is None:  # the SDK itself is missing: not a statement about the principal
            return _cannot_run(str(exc))
        print(f"oci principal: NOT obtainable ({_describe(exc)})")
        return EXIT_NO_PRINCIPAL
    print("oci principal: obtained")

    client = boto3.session.Session().client(
        "s3",
        endpoint_url=config.endpoint_url,
        region_name="auto",
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            s3={"addressing_style": "path"},
        ),
    )
    destination = S3MediaStorage(
        endpoint_url=config.endpoint_url, bucket=config.bucket, region="auto",
        access_key_id=config.access_key_id, secret_access_key=config.secret_access_key, client=client,
    )  # fmt: skip

    class Admin:
        async def put_bytes(self, key: str, data: bytes) -> None:
            await asyncio.to_thread(client.put_object, Bucket=config.bucket, Key=key, Body=data, ContentType="image/jpeg")

        async def delete(self, key: str) -> None:
            await asyncio.to_thread(client.delete_object, Bucket=config.bucket, Key=key)

    created: set[str] = set()
    results: list[CheckResult] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="media-restore-smoke-") as scratch:
            results = await run_checks(
                reader,
                destination,
                Admin(),
                Path(scratch),
                run_id=args.run_id,
                destination_bucket=config.bucket,
                forbidden_buckets=config.forbidden_buckets,
                created=created,
            )
    except (SmokeCannotRun, ms.PriorRunError) as exc:
        return _cannot_run(str(exc) if isinstance(exc, SmokeCannotRun) else "the drill run cannot be used")
    finally:
        removed = 0
        for key in sorted(created):
            try:
                client.delete_object(Bucket=config.bucket, Key=key)
                removed += 1
            except Exception as exc:  # noqa: BLE001 - cleanup is reported, never hidden; only the exception type is printed
                print(f"cleanup: could not delete a synthetic object ({type(exc).__name__})", file=sys.stderr)
        print(f"cleanup: {removed}/{len(created)} synthetic objects removed from the drill-restore bucket")
    assert results is not None
    print(format_report(results, args.run_id))
    return EXIT_PASS if all(r.passed for r in results) else EXIT_FAIL


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    return asyncio.run(amain(build_parser().parse_args(argv), os.environ if env is None else env))


if __name__ == "__main__":
    sys.exit(main())

