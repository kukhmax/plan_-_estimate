"""Make a purge ledger for the REHEARSAL in the drill bucket (archive cleanup AC-3; operator tool, owner workstation).

The rehearsal of `purge_backup_objects.py` must run on real objects but never on the production bucket. This tool only READS the drill bucket
(`plan-estimate-backup-drill`, nothing else is accepted): it lists `photos/v1/`, picks complete file sets (an original, a display and a thumbnail of
one asset) and writes them as a purge ledger file, with the sizes the bucket reports and a placeholder SHA-256 (the cleaning tool does not use it).

    python scripts/purge_rehearsal_ledger.py --namespace <ns> --config ~/.oci-purge/config --out /abs/new/rehearsal-ledger.jsonl [--count 1]

Then: `purge_backup_objects.py --ledger <that file> --bucket plan-estimate-backup-drill ...` (dry run first, then `--execute`). The drill objects it
removes are drill data; the production bucket is never named by this tool. Never printed: keys, the namespace, key material.
Exit codes: 0 written, 2 cannot run (no complete file set, bad input).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backup.purge_ledger import LedgerEntry, serialize_ledger

DRILL_BUCKET = "plan-estimate-backup-drill"
DEFAULT_REGION = "eu-frankfurt-1"
PREFIX = "photos/v1/"
PLACEHOLDER_SHA = "0" * 64
_KEY = re.compile(r"^photos/v1/([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})/(original\.[a-z0-9]{2,5}|display\.jpg|thumb\.jpg)$")
MAX_PAGES = 200


def describe_error(exc: BaseException) -> str:
    """What a failure may say: the exception type and, for an OCI service error, its HTTP status and error code (neither is secret)."""
    status, code = getattr(exc, "status", None), getattr(exc, "code", None)
    if isinstance(status, int) and isinstance(code, str):
        return f"{type(exc).__name__}, HTTP {status}, {code}"
    return type(exc).__name__


def list_sizes(client: Any, namespace: str, bucket: str) -> dict[str, int]:
    """name -> size of the objects under photos/v1/ (pages followed by `next_start_with`)."""
    sizes: dict[str, int] = {}
    start: str | None = None
    for _ in range(MAX_PAGES):
        kwargs: dict[str, Any] = {"prefix": PREFIX, "fields": "name,size"}
        if start:
            kwargs["start"] = start
        data = client.list_objects(namespace, bucket, **kwargs).data
        for item in data.objects or []:
            sizes[item.name] = int(item.size)
        start = getattr(data, "next_start_with", None)
        if not start:
            return sizes
    raise RuntimeError("the listing did not end")


def complete_sets(sizes: dict[str, int]) -> list[tuple[uuid.UUID, dict[str, str]]]:
    found: dict[str, dict[str, str]] = {}
    for name in sizes:
        match = _KEY.match(name)
        if match:
            role = "original" if match.group(2).startswith("original.") else ("display" if match.group(2) == "display.jpg" else "thumbnail")
            found.setdefault(match.group(1), {}).setdefault(role, name)
    return [(uuid.UUID(asset), roles) for asset, roles in sorted(found.items()) if set(roles) == {"original", "display", "thumbnail"}]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--config", required=True)
    parser.add_argument("--profile", default="DEFAULT")
    parser.add_argument("--out", required=True, help="absolute path of a NEW ledger file")
    parser.add_argument("--count", type=int, default=1, help="how many complete file sets to put in the rehearsal ledger (1-10)")
    return parser


def real_client(args: argparse.Namespace) -> Any:
    import oci

    config = oci.config.from_file(os.path.expanduser(args.config), args.profile)
    config["region"] = args.region
    return oci.object_storage.ObjectStorageClient(config, retry_strategy=oci.retry.NoneRetryStrategy())


def main(argv: Sequence[str], out: TextIO = sys.stdout, *, make_client: Callable[[argparse.Namespace], Any] = real_client,
         now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> int:
    args = build_parser().parse_args(list(argv))
    target = Path(args.out)
    if not target.is_absolute() or os.path.lexists(target) or not target.parent.is_dir() or not 1 <= args.count <= 10:
        print("refused: --out must be an absolute path of a new file in an existing directory, and --count 1..10", file=out)
        return 2
    try:
        sizes = list_sizes(make_client(args), args.namespace, DRILL_BUCKET)
    except Exception as exc:  # noqa: BLE001
        print(f"cannot run: the drill bucket cannot be read ({describe_error(exc)})", file=out)
        return 2
    sets = complete_sets(sizes)
    if not sets:
        print("cannot run: the drill bucket holds no complete photo file set to rehearse on", file=out)
        return 2
    stamp = now().strftime("%Y-%m-%dT%H:%M:%SZ")
    entries = [
        LedgerEntry(
            id=uuid.uuid4(), asset_id=asset, storage_name="rehearsal", key_original=roles["original"], key_display=roles["display"],
            key_thumbnail=roles["thumbnail"], sha256=PLACEHOLDER_SHA, size_original=max(sizes[roles["original"]], 1),
            size_display=max(sizes[roles["display"]], 1), size_thumbnail=max(sizes[roles["thumbnail"]], 1), purged_at=stamp,
        )
        for asset, roles in sets[: args.count]
    ]
    data = serialize_ledger(entries, exported_at=stamp)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    print(f"rehearsal ledger written: file_sets={len(entries)} (of {len(sets)} complete in the drill bucket)", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
