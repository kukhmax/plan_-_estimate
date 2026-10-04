"""Stage 14D.2F OCI backup-writer smoke (operator tool; DRILL bucket only).

Runs the production write path -- `OciBackupTarget` + `put_verified` +
`publish_run` -- against the real drill bucket with the VM's instance principal
(docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §16.9, docs/STAGE_14D4_CONNECTIVITY_SEMANTICS_SMOKE.md §12).
Everything it stores is synthetic: random bytes standing in for the encrypted
dump, an empty-READY-set manifest and its COMPLETE.json. It refuses any bucket
whose name does not contain "drill".

  1  instance principal obtained
  2  put_verified creates a new object (full re-download SHA-256 match)
  3  the same bytes again are an idempotent success (created=False)
  4  different bytes under the same key are refused (MediaObjectConflict)
  5  the object is unchanged afterwards (size, SHA-256)
  6  publish_run writes dump, manifest and COMPLETE.json (in that order)
  7  the stored manifest + COMPLETE.json verify (`verify_run`)
  8  the stored dump equals the local bytes
  9  publishing the same run again with a different seal is refused
 10  the stored COMPLETE.json is unchanged

Objects stay in the drill bucket (the uploader principal cannot delete, by
design): `smoke/14d2f/<run_id>/...`, `db/<run_id>/...`, `runs/<run_id>/...`.
Cleanup is a manual owner step with the administrator account.

Run it in a disposable container on the uploader network, with the backend
source mounted read-only and the pinned requirements installed:

    python stage14d2f_oci_writer_smoke.py --namespace <ns>

Output: one line per check. Never printed: tokens, OCIDs, namespace, object
contents, provider messages.
Exit codes: 0 all PASS, 1 a check failed, 2 cannot run, 3 no instance principal.
"""

import argparse
import asyncio
import hashlib
import os
import secrets
import sys
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.backup import manifest as mf
from app.backup import target as tg
from app.backup.run_id import new_run_id
from app.domain.exceptions import MediaObjectConflict, MediaStorageError
from app.domain.services.media_backup_ready_set import ready_set_digest

EXIT_PASS, EXIT_FAIL, EXIT_CANNOT_RUN, EXIT_NO_PRINCIPAL = 0, 1, 2, 3
DEFAULT_DRILL_BUCKET = "plan-estimate-backup-drill"
SYNTHETIC_RECIPIENTS = ("age1" + "q" * 58, "age1" + "p" * 58)  # well-formed, not real keys
DUMP_BYTES = 256 * 1024


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


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


async def _read(target: tg.BackupTarget, key: str, scratch: Path) -> bytes:
    workdir = Path(tempfile.mkdtemp(prefix="read-", dir=scratch))
    try:
        path = workdir / "object"
        await target.download_to(key, path)
        return path.read_bytes()
    finally:
        for child in workdir.iterdir():
            child.unlink()
        workdir.rmdir()


async def run_checks(
    target: tg.BackupTarget,
    scratch: Path,
    *,
    now: datetime,
    run_id: str,
    retry: tg.RetryPolicy = tg.DEFAULT_RETRY,
) -> list[CheckResult]:
    rec = Recorder()
    work = Path(tempfile.mkdtemp(prefix="smoke-", dir=scratch))
    object_key = f"smoke/14d2f/{run_id}/object.bin"
    payload = secrets.token_bytes(64 * 1024)
    other = secrets.token_bytes(64 * 1024)
    source, different = work / "payload", work / "different"
    source.write_bytes(payload)
    different.write_bytes(other)
    put = partial(tg.put_verified, target, content_type="application/octet-stream", scratch_dir=scratch, retry=retry)

    async def created() -> str:
        result = await put(key=object_key, source=source, expected_sha256=_sha(payload))
        if not result.created:
            raise AssertionError("expected a newly created object")
        return f"{result.size} bytes, SHA-256 verified by full re-download"

    async def idempotent() -> str:
        result = await put(key=object_key, source=source)
        if result.created:
            raise AssertionError("the second put must not create")
        return "already present, identical bytes verified"

    async def conflict() -> str:
        try:
            await put(key=object_key, source=different)
        except MediaObjectConflict:
            return "refused with MediaObjectConflict"
        raise AssertionError("different bytes were accepted under an existing key")

    async def unchanged() -> str:
        facts = await target.head(object_key)
        stored = await _read(target, object_key, scratch)
        if facts is None or facts.size != len(payload) or stored != payload:
            raise AssertionError("the stored object changed")
        return "size and SHA-256 equal the original"

    await rec.check("principal_and_put_created", created)
    await rec.check("put_identical_is_idempotent", idempotent)
    await rec.check("put_different_bytes_refused", conflict)
    await rec.check("object_unchanged_after_conflict", unchanged)

    dump = work / "plan-estimate.sql.gz.age"
    dump_bytes = secrets.token_bytes(DUMP_BYTES)
    dump.write_bytes(dump_bytes)
    started = mf.format_timestamp(now)
    empty = ready_set_digest([])
    header = mf.ManifestHeader(
        run_id=run_id,
        started_at=started,
        tool_commit="0" * 40,
        source=mf.SourceInfo("smoke-source", "plan-estimate-media-drill-source"),
        target=mf.TargetInfo(DEFAULT_DRILL_BUCKET),
        db_dump=mf.DbDumpInfo(
            key=mf.db_dump_key(run_id),
            recipients=SYNTHETIC_RECIPIENTS,
            encrypted_sha256=_sha(dump_bytes),
            encrypted_size=len(dump_bytes),
            alembic_head="smoke",
            dumped_at=started,
        ),
        snapshot=mf.SnapshotInfo(empty.ready_count, empty.ready_set_sha256),
    )

    async def publish(clock: Callable[[], datetime]) -> tg.PublishedRun:
        return await tg.publish_run(
            target,
            header=header,
            objects=[],
            dump_path=dump,
            source_keys=0,
            orphan_candidates=0,
            scratch_dir=scratch,
            retry=retry,
            clock=clock,
        )

    published: list[tg.PublishedRun] = []

    async def publish_first() -> str:
        run = await publish(lambda: datetime.now(UTC))
        published.append(run)
        return "dump, manifest and COMPLETE.json written; objects=0"

    async def stored_run_verifies() -> str:
        run = published[0]
        sealed = mf.verify_run(await _read(target, run.complete_key, scratch), await _read(target, run.manifest_key, scratch))
        return f"verify_run OK (run_id matches: {sealed.run_id == run_id})"

    async def stored_dump_matches() -> str:
        if await _read(target, header.db_dump.key, scratch) != dump_bytes:
            raise AssertionError("the stored dump differs")
        return "stored dump equals the local bytes"

    async def republish_refused() -> str:
        try:
            await publish(lambda: datetime.now(UTC) + timedelta(hours=1))
        except MediaObjectConflict:
            return "a different seal for the same run was refused"
        raise AssertionError("a second, different COMPLETE.json was accepted")

    async def seal_unchanged() -> str:
        run = published[0]
        if _sha(await _read(target, run.complete_key, scratch)) != run.complete_sha256:
            raise AssertionError("the stored COMPLETE.json changed")
        return "COMPLETE.json bytes unchanged"

    if await rec.check("publish_run_zero_asset", publish_first):
        await rec.check("stored_run_verifies", stored_run_verifies)
        await rec.check("stored_dump_matches", stored_dump_matches)
        await rec.check("republish_different_seal_refused", republish_refused)
        await rec.check("seal_unchanged", seal_unchanged)
    else:
        for name in ("stored_run_verifies", "stored_dump_matches", "republish_different_seal_refused", "seal_unchanged"):
            rec.results.append(CheckResult(name, False, "skipped: the run was not published"))
    for leftover in work.iterdir():
        leftover.unlink()
    work.rmdir()
    return rec.results


def format_report(results: list[CheckResult], run_id: str) -> str:
    lines = [f"{'check':36} result  detail"]
    lines.extend(f"{r.name:36} {'PASS' if r.passed else 'FAIL':6}  {r.detail}" for r in results)
    failed = sum(not r.passed for r in results)
    lines += ["", f"drill run_id (objects stay in the drill bucket): {run_id}"]
    lines.append(f"RESULT: {'PASS' if failed == 0 else 'FAIL'} ({len(results) - failed}/{len(results)} checks passed)")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--namespace", default=os.environ.get("OCI_NAMESPACE", ""), help="Object Storage namespace")
    parser.add_argument("--bucket", default=DEFAULT_DRILL_BUCKET)
    parser.add_argument("--region", default="eu-frankfurt-1")
    return parser


async def amain(args: argparse.Namespace) -> int:
    if "drill" not in args.bucket:
        print(f"cannot run: refusing to write to bucket {args.bucket!r} (not a drill bucket)", file=sys.stderr)
        return EXIT_CANNOT_RUN
    if not args.namespace:
        print("cannot run: --namespace (or OCI_NAMESPACE) is required", file=sys.stderr)
        return EXIT_CANNOT_RUN
    from app.backup.oci_target import OciBackupTarget

    try:
        target = OciBackupTarget.from_instance_principal(namespace=args.namespace, bucket=args.bucket, region=args.region)
    except MediaStorageError as exc:
        if exc.error_code is None:  # the SDK itself is missing: not a statement about the principal
            print(f"cannot run: {exc}", file=sys.stderr)
            return EXIT_CANNOT_RUN
        print(f"instance principal: NOT obtainable ({_describe(exc)})")
        return EXIT_NO_PRINCIPAL
    print("instance principal: obtained")
    run_id = new_run_id()
    with tempfile.TemporaryDirectory(prefix="oci-writer-smoke-") as scratch:
        results = await run_checks(target, Path(scratch), now=datetime.now(UTC), run_id=run_id)
    print(format_report(results, run_id))
    return EXIT_PASS if all(r.passed for r in results) else EXIT_FAIL


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(amain(build_parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
