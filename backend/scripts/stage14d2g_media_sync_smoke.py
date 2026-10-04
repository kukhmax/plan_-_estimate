"""Stage 14D.2G media-sync live smoke (operator tool; DRILL buckets only).

Runs the production copy path -- `S3MediaStorage` (R2 drill source) -> `sync_media` -> `OciBackupTarget`
(Oracle drill bucket, instance principal) -> `publish_run` / `load_prior_run` -- on synthetic assets
(docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §16.11). Nothing real is read or written: random bytes under fresh
`photos/v1/<uuid>/` keys. It refuses any bucket whose name does not contain "drill" and an R2 bucket equal
to the Oracle bucket.

Scenario (three good assets, three planted problems, two junk source keys):

  run 1  good assets, no prior run   every object copied, post-copy verified; the run is published
  run 2  same assets, prior = run 1  every object inherited; nothing downloaded from R2 or Oracle; published
  run 3  same, prior = run 2, deep   every object verified by download and compared with the source
  run 4  good + planted, prior = 2   exactly the planted failures, nothing published, nothing overwritten:
                                     a source object missing, an original whose bytes differ from the
                                     database SHA-256, a target object holding different bytes

  1  run1_copies_all                          10  source_listing_counts
  2  run1_publishes_and_verifies              11  report_is_secret_free
  3  run2_inherits_without_any_download
  4  run2_publishes_with_inherited_provenance
  5  run3_deep_verifies_by_download
  6  run4_reports_exactly_the_planted_failures
  7  run4_cannot_be_published
  8  conflicting_target_object_unchanged
  9  refused_objects_not_created

Configuration (environment; an env file passed with `docker run --env-file`, chmod 600, outside the repository):

    R2_ENDPOINT_URL        https://<account-id>.eu.r2.cloudflarestorage.com (EU jurisdiction)
    R2_ACCESS_KEY_ID       drill token access key id (Object Read & Write on the drill source bucket)
    R2_SECRET_ACCESS_KEY   drill token secret
    R2_BUCKET              the drill SOURCE bucket (name must contain "drill")
    OCI_NAMESPACE          Object Storage namespace (or --namespace)

The Oracle drill bucket is `--bucket` (default plan-estimate-backup-drill). The synthetic R2 objects are deleted
at the end; the Oracle objects stay (the uploader principal cannot delete, by design): `photos/v1/<uuid>/...`
(prefixes are printed), `db/<run_id>/...`, `runs/<run_id>/...`. Cleanup is a manual administrator step.

Output: one line per check. Never printed: credentials, endpoint, namespace, keys, object contents, provider
messages. Exit codes: 0 all PASS, 1 a check failed, 2 cannot run, 3 no instance principal.
"""

import argparse
import asyncio
import hashlib
import os
import re
import secrets
import sys
import tempfile
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.backup import manifest as mf
from app.backup import media_sync as ms
from app.backup import target as tg
from app.backup.run_id import new_run_id
from app.domain.exceptions import MediaStorageError
from app.domain.photos.keys import PHOTO_KEY_PREFIX
from app.domain.services.media_backup_ready_set import ReadyAsset, ready_set_digest
from app.domain.services.media_storage import MediaStorageAdmin

EXIT_PASS, EXIT_FAIL, EXIT_CANNOT_RUN, EXIT_NO_PRINCIPAL = 0, 1, 2, 3
DEFAULT_DRILL_BUCKET = "plan-estimate-backup-drill"
SYNTHETIC_RECIPIENTS = ("age1" + "q" * 58, "age1" + "p" * 58)  # well-formed, not real keys
EU_ENDPOINT = re.compile(r"^https://[0-9a-f]{32}\.eu\.r2\.cloudflarestorage\.com/?$")
BUCKET_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
ORIGINAL_BYTES, DISPLAY_BYTES, THUMB_BYTES = 48 * 1024, 12 * 1024, 4 * 1024
JUNK_KEYS = 2


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class SmokeOutcome:
    results: list[CheckResult]
    uploaded_keys: list[str]  # synthetic objects put into the R2 drill source bucket
    asset_prefixes: list[str]  # photos/v1/<uuid>/ prefixes that stay in the Oracle drill bucket
    run_ids: list[str]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


# --- counting wrappers ---------------------------------------------------------------------------------


class CountingSource:
    def __init__(self, inner: MediaStorageAdmin) -> None:
        self.inner = inner
        self.downloads = 0

    async def download_to(self, key: str, path: Path) -> None:
        self.downloads += 1
        await self.inner.download_to(key, path)

    def iter_keys(self, prefix: str) -> AsyncIterator[str]:
        return self.inner.iter_keys(prefix)


class CountingTarget:
    def __init__(self, inner: tg.BackupTarget) -> None:
        self.inner = inner
        self.downloads = 0
        self.puts = 0

    async def put_new(self, key: str, source: Path, content_type: str) -> tg.PutOutcome:
        self.puts += 1
        return await self.inner.put_new(key, source, content_type)

    async def head(self, key: str) -> tg.TargetObject | None:
        return await self.inner.head(key)

    async def download_to(self, key: str, path: Path) -> None:
        self.downloads += 1
        await self.inner.download_to(key, path)


# --- synthetic fixture ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FixtureAsset:
    ready: ReadyAsset
    stored: dict[str, bytes]  # key -> the bytes that go into the source store (a missing key is simply absent)
    kind: str


def build_asset(kind: str, extension: str) -> FixtureAsset:
    asset_id = uuid.uuid4()
    base = f"{PHOTO_KEY_PREFIX}{asset_id}/"
    original, display, thumb = (secrets.token_bytes(n) for n in (ORIGINAL_BYTES, DISPLAY_BYTES, THUMB_BYTES))
    keys = (f"{base}original.{extension}", f"{base}display.jpg", f"{base}thumb.jpg")
    ready = ReadyAsset(asset_id, *keys, len(original), len(display), len(thumb), _sha(original))
    stored = {keys[0]: original, keys[1]: display, keys[2]: thumb}
    if kind == "missing":
        del stored[keys[1]]  # READY in the database, absent in the source store
    elif kind == "bad_sha":
        stored[keys[0]] = bytes([original[0] ^ 0xFF]) + original[1:]  # same size, other bytes
    return FixtureAsset(ready, stored, kind)


def _store_path(scratch: Path, data: bytes) -> Path:
    path = Path(tempfile.mkdtemp(prefix="fixture-", dir=scratch)) / "object"
    path.write_bytes(data)
    return path


async def _upload(source: MediaStorageAdmin, scratch: Path, key: str, data: bytes) -> None:
    path = _store_path(scratch, data)
    try:
        await source.put_object(key, path, "application/octet-stream")
    finally:
        path.unlink()
        path.parent.rmdir()


async def _count_keys(source: MediaStorageAdmin) -> int:
    return sum([1 async for _ in source.iter_keys(PHOTO_KEY_PREFIX)])


def _header(
    assets: list[ReadyAsset], run_id: str, source_bucket: str, target_bucket: str, dump: bytes, now: datetime
) -> mf.ManifestHeader:
    digest = ready_set_digest(assets)
    started = mf.format_timestamp(now)
    return mf.ManifestHeader(
        run_id=run_id,
        started_at=started,
        tool_commit="0" * 40,
        source=mf.SourceInfo("smoke-source", source_bucket),
        target=mf.TargetInfo(target_bucket),
        db_dump=mf.DbDumpInfo(
            key=mf.db_dump_key(run_id),
            recipients=SYNTHETIC_RECIPIENTS,
            encrypted_sha256=_sha(dump),
            encrypted_size=len(dump),
            alembic_head="smoke",
            dumped_at=started,
        ),
        snapshot=mf.SnapshotInfo(digest.ready_count, digest.ready_set_sha256),
    )


# --- the checks ----------------------------------------------------------------------------------------------


async def run_checks(
    raw_source: MediaStorageAdmin,
    raw_target: tg.BackupTarget,
    scratch: Path,
    *,
    now: datetime,
    source_bucket: str,
    target_bucket: str,
    uploaded: list[str],
    retry: tg.RetryPolicy = tg.DEFAULT_RETRY,
) -> SmokeOutcome:
    """`uploaded` receives every synthetic key put into the source store, even if a later step raises,
    so the caller can always clean up."""
    rec = Recorder()
    source, target = CountingSource(raw_source), CountingTarget(raw_target)
    run_ids = [new_run_id(now + timedelta(seconds=n)) for n in range(4)]
    good = [build_asset("good", ext) for ext in ("jpg", "png", "webp")]
    missing, bad_sha, conflict = build_asset("missing", "jpg"), build_asset("bad_sha", "png"), build_asset("conflict", "jpg")
    planted = [missing, bad_sha, conflict]
    junk = [f"{PHOTO_KEY_PREFIX}{uuid.uuid4()}/original.jpg" for _ in range(JUNK_KEYS)]
    good_ready = [item.ready for item in good]
    all_ready = good_ready + [item.ready for item in planted]

    baseline = await _count_keys(raw_source)
    for item in [*good, *planted]:
        for key, data in item.stored.items():
            await _upload(raw_source, scratch, key, data)
            uploaded.append(key)
    for key in junk:
        await _upload(raw_source, scratch, key, secrets.token_bytes(1024))
        uploaded.append(key)
    prefixes = [f"{PHOTO_KEY_PREFIX}{item.ready.asset_id}/" for item in [*good, *planted]]

    conflict_key = conflict.ready.key_display
    planted_target_bytes = bytes([conflict.stored[conflict_key][0] ^ 0xFF]) + conflict.stored[conflict_key][1:]
    path = _store_path(scratch, planted_target_bytes)
    try:
        await raw_target.put_new(conflict_key, path, "image/jpeg")  # create-only: this is the only way to plant it
    finally:
        path.unlink()
        path.parent.rmdir()

    async def sync(
        assets: list[ReadyAsset], run_id: str, prior: mf.VerifiedRun | None = None, deep: bool = False
    ) -> ms.MediaSyncResult:
        source.downloads = target.downloads = target.puts = 0
        return await ms.sync_media(
            source,
            target,
            assets=assets,
            run_id=run_id,
            target_bucket=target_bucket,
            scratch_dir=scratch,
            prior=prior,
            deep=deep,
            retry=retry,
            clock=lambda: datetime.now(UTC),
        )

    async def publish(result: ms.MediaSyncResult, assets: list[ReadyAsset], run_id: str) -> mf.VerifiedRun:
        dump = secrets.token_bytes(64 * 1024)
        dump_path = _store_path(scratch, dump)
        try:
            await tg.publish_run(
                target,
                header=_header(assets, run_id, source_bucket, target_bucket, dump, now),
                objects=result.objects_for_publication(),
                dump_path=dump_path,
                source_keys=result.source_keys,
                orphan_candidates=result.orphan_candidates,
                scratch_dir=scratch,
                retry=retry,
            )
        finally:
            dump_path.unlink()
            dump_path.parent.rmdir()
        return await ms.load_prior_run(target, run_id, scratch_dir=scratch, retry=retry)

    state: dict[str, object] = {}

    async def run1_copies_all() -> str:
        result = await sync(good_ready, run_ids[0])
        state["run1"] = result
        if not result.complete or result.counts.copied != 9 or result.counts.inherited or result.counts.verified_present:
            raise AssertionError("expected nine objects copied and nothing else")
        return f"9 objects copied ({result.counts.bytes_copied} bytes), each verified by full re-download"

    async def run1_publishes() -> str:
        result = state["run1"]
        assert isinstance(result, ms.MediaSyncResult)
        state["prior1"] = await publish(result, good_ready, run_ids[0])
        return "dump, manifest and COMPLETE.json written; verify_run OK"

    async def run2_inherits() -> str:
        prior = state["prior1"]
        assert isinstance(prior, mf.VerifiedRun)
        result = await sync(good_ready, run_ids[1], prior=prior)
        state["run2"] = result
        if not result.complete or result.counts.inherited != 9 or result.counts.copied or result.counts.verified_present:
            raise AssertionError("expected nine objects inherited")
        if (source.downloads, target.downloads, target.puts) != (0, 0, 0):
            raise AssertionError("an inherited object must not be downloaded or written")
        return "9 objects inherited; 0 downloads from R2, 0 from Oracle, 0 writes"

    async def run2_publishes() -> str:
        result = state["run2"]
        assert isinstance(result, ms.MediaSyncResult)
        prior2 = await publish(result, good_ready, run_ids[1])
        state["prior2"] = prior2
        if {obj.sha_provenance for obj in prior2.manifest.objects} != {f"inherited:{run_ids[0]}"}:
            raise AssertionError("provenance is not inherited from run 1")
        return "published; every object line says inherited from run 1"

    async def run3_deep() -> str:
        prior = state["prior2"]
        assert isinstance(prior, mf.VerifiedRun)
        result = await sync(good_ready, run_ids[2], prior=prior, deep=True)
        if not result.complete or result.counts.verified_present != 9 or result.counts.inherited or result.counts.copied:
            raise AssertionError("expected nine objects verified by download")
        if (source.downloads, target.downloads) != (9, 9):
            raise AssertionError("deep mode must download every object from both stores")
        return "9 objects verified by download from R2 and Oracle and compared"

    async def run4_failures() -> str:
        prior = state["prior2"]
        assert isinstance(prior, mf.VerifiedRun)
        result = await sync(all_ready, run_ids[3], prior=prior)
        state["run4"] = result
        wanted = {
            (str(missing.ready.asset_id), mf.Role.DISPLAY, ms.FailureCode.MISSING_SOURCE),
            (str(bad_sha.ready.asset_id), mf.Role.ORIGINAL, ms.FailureCode.SOURCE_SHA_MISMATCH),
            (str(conflict.ready.asset_id), mf.Role.DISPLAY, ms.FailureCode.TARGET_CONFLICT),
        }
        found = {(f.asset_id, f.role, f.code) for f in result.failures}
        if found != wanted or len(result.failures) != 3 or result.aborted is not None:
            raise AssertionError("the failures are not exactly the planted ones")
        if result.counts.inherited != 9 or result.counts.copied != 6:
            raise AssertionError("good assets must be inherited and the rest of the planted assets copied")
        return "3 failures (missing source, source SHA mismatch, target conflict); 9 inherited, 6 copied"

    async def run4_not_publishable() -> str:
        result = state["run4"]
        assert isinstance(result, ms.MediaSyncResult)
        try:
            result.objects_for_publication()
        except ms.MediaSyncIncomplete:
            return "objects_for_publication refused: no manifest can be built"
        raise AssertionError("an incomplete run handed out its objects")

    async def conflict_unchanged() -> str:
        workdir = Path(tempfile.mkdtemp(prefix="read-", dir=scratch))
        try:
            await raw_target.download_to(conflict_key, workdir / "object")
            if (workdir / "object").read_bytes() != planted_target_bytes:
                raise AssertionError("the conflicting target object changed")
        finally:
            for child in workdir.iterdir():
                child.unlink()
            workdir.rmdir()
        return "the existing object is byte-identical: nothing is overwritten"

    async def refused_not_created() -> str:
        for key in (missing.ready.key_display, bad_sha.ready.key_original):
            if await raw_target.head(key) is not None:
                raise AssertionError("an object that failed its source checks was created")
        return "no target object exists for the missing-source and SHA-mismatch keys"

    async def listing_counts() -> str:
        run1, run4 = state["run1"], state["run4"]
        assert isinstance(run1, ms.MediaSyncResult) and isinstance(run4, ms.MediaSyncResult)
        total = baseline + len(uploaded)
        planted_present = sum(len(item.stored) for item in planted)
        if (run1.source_keys, run1.orphan_candidates) != (total, total - 9):
            raise AssertionError("run 1 listing counts are wrong")
        if (run4.source_keys, run4.orphan_candidates) != (total, baseline + JUNK_KEYS):
            raise AssertionError("run 4 listing counts are wrong")
        return f"source keys {total} (baseline {baseline}, good 9, planted {planted_present}, junk {JUNK_KEYS}); orphans counted, never copied"

    async def report_secret_free() -> str:
        result = state["run4"]
        assert isinstance(result, ms.MediaSyncResult)
        text = result.report_bytes().decode()
        secrets_found = [PHOTO_KEY_PREFIX in text, *(_sha(data) in text for item in good for data in item.stored.values())]
        if any(secrets_found) or "MISSING_SOURCE" not in text:
            raise AssertionError("the report leaks object names / hashes or lacks the failure codes")
        return "report lists failure codes and asset ids only"

    steps: tuple[tuple[str, Callable[[], Awaitable[str]]], ...] = (
        ("run1_copies_all", run1_copies_all),
        ("run1_publishes_and_verifies", run1_publishes),
        ("run2_inherits_without_any_download", run2_inherits),
        ("run2_publishes_with_inherited_provenance", run2_publishes),
        ("run3_deep_verifies_by_download", run3_deep),
        ("run4_reports_exactly_the_planted_failures", run4_failures),
        ("run4_cannot_be_published", run4_not_publishable),
        ("conflicting_target_object_unchanged", conflict_unchanged),
        ("refused_objects_not_created", refused_not_created),
        ("source_listing_counts", listing_counts),
        ("report_is_secret_free", report_secret_free),
    )
    stopped = False  # the steps build on each other (sealed runs are the next run's prior)
    for name, step in steps:
        if stopped:
            rec.results.append(CheckResult(name, False, "skipped: an earlier check failed"))
        elif not await rec.check(name, step):
            stopped = True
    return SmokeOutcome(rec.results, uploaded, prefixes, run_ids)


def format_report(outcome: SmokeOutcome) -> str:
    lines = [f"{'check':44} result  detail"]
    lines.extend(f"{r.name:44} {'PASS' if r.passed else 'FAIL':6}  {r.detail}" for r in outcome.results)
    failed = sum(not r.passed for r in outcome.results)
    lines += ["", "runs (published runs stay in the Oracle drill bucket): " + ", ".join(outcome.run_ids)]
    lines.append("Oracle objects that stay (administrator cleanup):")
    lines.extend(f"  {prefix}" for prefix in outcome.asset_prefixes)
    lines.append(f"RESULT: {'PASS' if failed == 0 else 'FAIL'} ({len(outcome.results) - failed}/{len(outcome.results)} checks passed)")
    return "\n".join(lines)


# --- configuration and entry point --------------------------------------------------------------------------


@dataclass(frozen=True)
class R2Config:
    endpoint_url: str
    access_key_id: str
    secret_access_key: str
    bucket: str

    def __repr__(self) -> str:  # never expose credentials or the account id
        return f"R2Config(bucket={self.bucket!r})"


def load_r2_config(env: Mapping[str, str]) -> R2Config:
    """Validate the environment; raises ValueError naming the variable only."""
    endpoint = env.get("R2_ENDPOINT_URL", "").strip()
    key_id = env.get("R2_ACCESS_KEY_ID", "").strip()
    secret = env.get("R2_SECRET_ACCESS_KEY", "").strip()
    bucket = env.get("R2_BUCKET", "").strip()
    if not EU_ENDPOINT.match(endpoint):
        raise ValueError("R2_ENDPOINT_URL must be the EU-jurisdiction https endpoint")
    if not key_id or not secret:
        raise ValueError("R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY are required")
    if not BUCKET_NAME.match(bucket):
        raise ValueError("R2_BUCKET is not a valid bucket name")
    if "drill" not in bucket:
        raise ValueError("refusing to run: R2_BUCKET is not a drill bucket")
    return R2Config(endpoint, key_id, secret, bucket)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--namespace", default=os.environ.get("OCI_NAMESPACE", ""), help="Object Storage namespace")
    parser.add_argument("--bucket", default=DEFAULT_DRILL_BUCKET, help="Oracle drill target bucket")
    parser.add_argument("--region", default="eu-frankfurt-1")
    return parser


def _cannot_run(message: str) -> int:
    print(f"cannot run: {message}", file=sys.stderr)
    return EXIT_CANNOT_RUN


async def amain(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    if "drill" not in args.bucket:
        return _cannot_run(f"refusing to write to bucket {args.bucket!r} (not a drill bucket)")
    if not args.namespace:
        return _cannot_run("--namespace (or OCI_NAMESPACE) is required")
    try:
        config = load_r2_config(env)
    except ValueError as exc:
        return _cannot_run(str(exc))
    if config.bucket == args.bucket:
        return _cannot_run("the R2 source bucket and the Oracle target bucket must differ")
    try:
        import boto3
        from botocore.config import Config

        from app.backup.oci_target import OciBackupTarget
        from app.core.s3_media_storage import S3MediaStorage
    except ImportError as exc:
        return _cannot_run(f"a required library is not installed ({type(exc).__name__})")

    try:
        target = OciBackupTarget.from_instance_principal(namespace=args.namespace, bucket=args.bucket, region=args.region)
    except MediaStorageError as exc:
        if exc.error_code is None:  # the SDK itself is missing: not a statement about the principal
            return _cannot_run(str(exc))
        print(f"instance principal: NOT obtainable ({_describe(exc)})")
        return EXIT_NO_PRINCIPAL
    print("instance principal: obtained")

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
    source = S3MediaStorage(
        endpoint_url=config.endpoint_url,
        bucket=config.bucket,
        region="auto",
        access_key_id=config.access_key_id,
        secret_access_key=config.secret_access_key,
        client=client,
    )
    uploaded: list[str] = []  # filled by run_checks, so cleanup also covers a run that stopped half way
    outcome: SmokeOutcome | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="media-sync-smoke-") as scratch:
            outcome = await run_checks(
                source,
                target,
                Path(scratch),
                now=datetime.now(UTC),
                source_bucket=config.bucket,
                target_bucket=args.bucket,
                uploaded=uploaded,
            )
    finally:
        removed = 0
        for key in uploaded:
            try:
                client.delete_object(Bucket=config.bucket, Key=key)
                removed += 1
            except Exception as exc:  # noqa: BLE001 - cleanup is reported, never hidden; only the exception type is printed
                print(f"cleanup: could not delete a synthetic R2 object ({type(exc).__name__})", file=sys.stderr)
        print(f"cleanup: {removed}/{len(uploaded)} synthetic R2 objects removed")
    if outcome is None:
        return EXIT_FAIL
    print(format_report(outcome))
    return EXIT_PASS if all(r.passed for r in outcome.results) else EXIT_FAIL


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    return asyncio.run(amain(build_parser().parse_args(argv), os.environ if env is None else env))


if __name__ == "__main__":
    sys.exit(main())
