"""Stage 14D.2H verify live smoke (operator tool; DRILL bucket, read-only).

Runs the production verification path -- `OciBackupTarget` (instance principal) behind a read-only wrapper
-> `verify_run_in_target` -- on runs that an earlier drill (the 14D.2G smoke) published in the Oracle drill
bucket (docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §16.12). NOTHING is written: the wrapper exposes `head` and
`download_to` only, and every negative case is produced by faults injected on the CLIENT side of an
unmodified, genuine stored run (flipped bytes, a changed size, a hidden object), never by changing the bucket.

  1  full_verify_passes                    seal, dump SHA-256 and every object's SHA-256 against the manifest
  2  quick_verify_reads_documents_only     two documents downloaded, nothing else; HEAD sizes only
  3  inherited_run_verified_by_download    (only with --run-id-2) FULL downloads every object, inherited or not
  4  unknown_run_reported                  a fresh run id has no seal
  5  recipient_mismatch_reported           a public recipient that is not in the manifest
  6  expected_recipients_accepted          (only with --expect-recipient) the real recipients are present
  7  flipped_bytes_detected                one object's bytes changed in transit -> SHA_MISMATCH for it alone
  8  changed_size_detected                 one HEAD size off by one -> SIZE_MISMATCH for it alone
  9  hidden_object_detected                one HEAD answers "absent" -> MISSING_OBJECT for it alone
 10  changed_dump_detected                 the dump's bytes changed in transit -> DUMP_SHA_MISMATCH
 11  report_is_secret_free

Run in a disposable container on the uploader network (the uploader principal can read; verification needs no
write permission):

    python stage14d2h_verify_smoke.py --namespace <ns> --run-id <run_id> [--run-id-2 <run_id>]
                                      [--expect-recipient age1...]

Output: one line per check. Never printed: namespace, keys, hashes, object contents, provider messages.
Exit codes: 0 all PASS, 1 a check failed, 2 cannot run, 3 no instance principal.
"""

import argparse
import asyncio
import dataclasses
import os
import secrets
import sys
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.backup import manifest as mf
from app.backup import media_sync as ms
from app.backup import target as tg
from app.backup import verify as vf
from app.backup.run_id import new_run_id, validate_run_id
from app.domain.exceptions import MediaStorageError

EXIT_PASS, EXIT_FAIL, EXIT_CANNOT_RUN, EXIT_NO_PRINCIPAL = 0, 1, 2, 3
DEFAULT_DRILL_BUCKET = "plan-estimate-backup-drill"
_ALPHABET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"  # bech32 data characters (the age recipient alphabet)


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


def random_recipient() -> str:
    """A well-formed public recipient that is certainly not in any manifest (random, never a real key)."""
    return "age1" + "".join(secrets.choice(_ALPHABET) for _ in range(58))


class ReadOnlyReader:
    """The genuine target seen through `head` and `download_to` only, with optional client-side faults."""

    def __init__(
        self,
        inner: tg.BackupReader,
        *,
        flip_download: str | None = None,
        resize_head: str | None = None,
        hide_head: str | None = None,
    ) -> None:
        self._inner = inner
        self._flip_download = flip_download
        self._resize_head = resize_head
        self._hide_head = hide_head
        self.downloads: list[str] = []

    async def head(self, key: str) -> tg.TargetObject | None:
        if key == self._hide_head:
            return None
        facts = await self._inner.head(key)
        if facts is not None and key == self._resize_head:
            return dataclasses.replace(facts, size=facts.size + 1)
        return facts

    async def download_to(self, key: str, path: Path) -> None:
        self.downloads.append(key)
        await self._inner.download_to(key, path)
        if key == self._flip_download:
            data = bytearray(path.read_bytes())
            data[0] ^= 0xFF
            path.write_bytes(bytes(data))


async def run_checks(
    target: tg.BackupReader,
    scratch: Path,
    *,
    run_id: str,
    run_id_2: str | None = None,
    expect_recipients: tuple[str, ...] = (),
    retry: tg.RetryPolicy = tg.DEFAULT_RETRY,
) -> list[CheckResult]:
    rec = Recorder()
    run = await ms.load_prior_run(target, run_id, scratch_dir=scratch, retry=retry)  # also proves the seal is readable
    objects = run.manifest.objects
    if len(objects) < 3:
        raise ValueError("the drill run needs at least three objects")
    flipped, resized, hidden = objects[0], objects[1], objects[2]
    dump_key = run.manifest.header.db_dump.key

    async def verify(
        reader: tg.BackupReader, which: str = run_id, mode: vf.VerifyMode = vf.VerifyMode.FULL, **kwargs: object
    ) -> vf.VerifyReport:
        return await vf.verify_run_in_target(reader, which, scratch_dir=scratch, mode=mode, retry=retry, **kwargs)  # type: ignore[arg-type]

    def only(report: vf.VerifyReport, obj: mf.ManifestObject, code: vf.ObjectProblemCode) -> bool:
        return report.object_problems == (vf.ObjectProblem(obj.asset_id, obj.role, code),) and not report.run_problems

    async def full_passes() -> str:
        report = await verify(ReadOnlyReader(target))
        if not report.ok or report.dump_checked != "sha256" or report.counts.sha_checked != len(objects):
            raise AssertionError("a genuine stored run must verify")
        return f"{report.counts.objects_total} objects, {report.counts.bytes_hashed} bytes hashed; dump SHA-256 matches"

    async def quick_reads_documents_only() -> str:
        reader = ReadOnlyReader(target)
        report = await verify(reader, mode=vf.VerifyMode.QUICK)
        expected = sorted([mf.complete_key(run_id), mf.manifest_key(run_id)])
        if not report.ok or sorted(reader.downloads) != expected or report.counts.sha_checked != 0:
            raise AssertionError("quick mode must read only the two documents")
        return f"{report.counts.size_checked} sizes checked by HEAD; 2 documents downloaded"

    async def inherited_run_by_download() -> str:
        assert run_id_2 is not None
        second = await ms.load_prior_run(target, run_id_2, scratch_dir=scratch, retry=retry)
        reader = ReadOnlyReader(target)
        report = await verify(reader, which=run_id_2)
        inherited = sum(1 for obj in second.manifest.objects if obj.sha_provenance != mf.DOWNLOADED)
        if not report.ok or report.counts.sha_checked != len(second.manifest.objects) or inherited == 0:
            raise AssertionError("the inherited run must verify by downloading every object")
        return f"{inherited} inherited lines, all {report.counts.sha_checked} verified by download"

    async def unknown_run() -> str:
        report = await verify(ReadOnlyReader(target), which=new_run_id())
        if report.run_problems != (vf.RunProblem.SEAL_MISSING,) or report.ok:
            raise AssertionError("an unknown run must have no seal")
        return "SEAL_MISSING"

    async def recipient_mismatch() -> str:
        report = await verify(ReadOnlyReader(target), mode=vf.VerifyMode.QUICK, expected_recipients=[random_recipient()])
        if report.run_problems != (vf.RunProblem.RECIPIENTS_MISMATCH,):
            raise AssertionError("an absent recipient must be reported")
        return "RECIPIENTS_MISMATCH for a recipient that is not in the manifest"

    async def recipients_accepted() -> str:
        report = await verify(ReadOnlyReader(target), mode=vf.VerifyMode.QUICK, expected_recipients=list(expect_recipients))
        if not report.ok:
            raise AssertionError("the expected recipients are not all in the manifest")
        return f"{len(expect_recipients)} expected recipient(s) present in the manifest"

    async def flipped_bytes() -> str:
        report = await verify(ReadOnlyReader(target, flip_download=flipped.key))
        if not only(report, flipped, vf.ObjectProblemCode.SHA_MISMATCH):
            raise AssertionError("exactly the tampered object must be reported")
        return "SHA_MISMATCH for the one object whose bytes were changed in transit"

    async def changed_size() -> str:
        report = await verify(ReadOnlyReader(target, resize_head=resized.key), mode=vf.VerifyMode.QUICK)
        if not only(report, resized, vf.ObjectProblemCode.SIZE_MISMATCH):
            raise AssertionError("exactly the resized object must be reported")
        return "SIZE_MISMATCH for the one object whose HEAD size was changed"

    async def hidden_object() -> str:
        report = await verify(ReadOnlyReader(target, hide_head=hidden.key), mode=vf.VerifyMode.QUICK)
        if not only(report, hidden, vf.ObjectProblemCode.MISSING_OBJECT):
            raise AssertionError("exactly the hidden object must be reported")
        return "MISSING_OBJECT for the one object that answered absent"

    async def changed_dump() -> str:
        report = await verify(ReadOnlyReader(target, flip_download=dump_key))
        if report.run_problems != (vf.RunProblem.DUMP_SHA_MISMATCH,) or report.object_problems:
            raise AssertionError("a changed dump must be reported alone")
        return "DUMP_SHA_MISMATCH"

    async def secret_free() -> str:
        report = await verify(ReadOnlyReader(target, flip_download=flipped.key))
        text = report.report_bytes().decode()
        leaks = [text.count("photos/v1"), text.count(run.manifest.header.db_dump.encrypted_sha256)]
        leaks += [text.count(obj.sha256) for obj in objects]
        leaks += [text.count(recipient) for recipient in run.manifest.header.db_dump.recipients]
        if any(leaks) or "SHA_MISMATCH" not in text:
            raise AssertionError("the report leaks object names, hashes or recipients, or lacks the problem code")
        return "report lists problem codes, asset ids and roles only"

    steps: list[tuple[str, Callable[[], Awaitable[str]]]] = [
        ("full_verify_passes", full_passes),
        ("quick_verify_reads_documents_only", quick_reads_documents_only),
    ]
    if run_id_2 is not None:
        steps.append(("inherited_run_verified_by_download", inherited_run_by_download))
    steps += [("unknown_run_reported", unknown_run), ("recipient_mismatch_reported", recipient_mismatch)]
    if expect_recipients:
        steps.append(("expected_recipients_accepted", recipients_accepted))
    steps += [
        ("flipped_bytes_detected", flipped_bytes),
        ("changed_size_detected", changed_size),
        ("hidden_object_detected", hidden_object),
        ("changed_dump_detected", changed_dump),
        ("report_is_secret_free", secret_free),
    ]
    for name, step in steps:
        await rec.check(name, step)
    return rec.results


def format_report(results: list[CheckResult], run_ids: list[str]) -> str:
    lines = [f"{'check':40} result  detail"]
    lines.extend(f"{r.name:40} {'PASS' if r.passed else 'FAIL':6}  {r.detail}" for r in results)
    failed = sum(not r.passed for r in results)
    lines += ["", "verified runs (read-only; nothing was written): " + ", ".join(run_ids)]
    lines.append(f"RESULT: {'PASS' if failed == 0 else 'FAIL'} ({len(results) - failed}/{len(results)} checks passed)")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--namespace", default=os.environ.get("OCI_NAMESPACE", ""), help="Object Storage namespace")
    parser.add_argument("--bucket", default=DEFAULT_DRILL_BUCKET)
    parser.add_argument("--region", default="eu-frankfurt-1")
    parser.add_argument("--run-id", required=True, help="a published drill run")
    parser.add_argument("--run-id-2", default=None, help="a later drill run that inherited from the first")
    parser.add_argument("--expect-recipient", action="append", default=[], help="a public age recipient the runs must name")
    return parser


def _cannot_run(message: str) -> int:
    print(f"cannot run: {message}", file=sys.stderr)
    return EXIT_CANNOT_RUN


async def amain(args: argparse.Namespace) -> int:
    if "drill" not in args.bucket:
        return _cannot_run(f"refusing to verify in bucket {args.bucket!r} (not a drill bucket)")
    if not args.namespace:
        return _cannot_run("--namespace (or OCI_NAMESPACE) is required")
    run_ids = [args.run_id] + ([args.run_id_2] if args.run_id_2 else [])
    for value in run_ids:
        try:
            validate_run_id(value)
        except ValueError:
            return _cannot_run("a run id is not in the canonical form YYYYMMDDTHHMMSSZ-xxxxxxxx")
    from app.backup.oci_target import OciBackupTarget

    try:
        target = OciBackupTarget.from_instance_principal(namespace=args.namespace, bucket=args.bucket, region=args.region)
    except MediaStorageError as exc:
        if exc.error_code is None:  # the SDK itself is missing: not a statement about the principal
            return _cannot_run(str(exc))
        print(f"instance principal: NOT obtainable ({_describe(exc)})")
        return EXIT_NO_PRINCIPAL
    print("instance principal: obtained")
    with tempfile.TemporaryDirectory(prefix="verify-smoke-") as scratch:
        try:
            results = await run_checks(
                target,
                Path(scratch),
                run_id=args.run_id,
                run_id_2=args.run_id_2,
                expect_recipients=tuple(args.expect_recipient),
            )
        except (ms.PriorRunError, ValueError) as exc:
            return _cannot_run(f"the drill run cannot be used ({type(exc).__name__})")
    print(format_report(results, run_ids))
    return EXIT_PASS if all(r.passed for r in results) else EXIT_FAIL


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(amain(build_parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
