"""Stage 14B.4 read-only media integrity check (operator tool).

Compares PhotoAsset rows with the objects of the configured media store.
Read-only by design: no object is written or deleted, no DB row changes
(PostgreSQL: the session runs in a READ ONLY transaction and is rolled
back), no URL is presigned, no credential is printed.

Usage (inside the backend environment, e.g. the backend container):

    python scripts/media_integrity_check.py
    python scripts/media_integrity_check.py --verify-sha256     # downloads READY originals
    python scripts/media_integrity_check.py --expect-storage-name r2-primary --strict
    python scripts/media_integrity_check.py --json

The store is the one configured by MEDIA_STORAGE_* settings. To verify an
independent backup target later, run with that target's settings and
`--expect-storage-name` set to the logical store whose rows it mirrors.

Exit codes: 0 clean (warnings allowed), 1 integrity errors (or warnings with
--strict), 2 the check could not run (storage disabled, unavailable or
misconfigured) -- an incomplete run is never reported as clean.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.domain.exceptions import MediaStorageError  # noqa: E402
from app.domain.services.media_integrity import format_report, run_integrity_check  # noqa: E402
from app.domain.services.media_storage import MediaStorageAdmin  # noqa: E402
from app.domain.services.photo_asset_service import PhotoAssetService  # noqa: E402

EXIT_CLEAN, EXIT_INTEGRITY_ERRORS, EXIT_CANNOT_RUN = 0, 1, 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--expect-storage-name", default=None, help="logical store whose rows to expect (default: MEDIA_STORAGE_NAME)"
    )
    parser.add_argument("--verify-sha256", action="store_true", help="download READY originals and compare sha256")
    parser.add_argument("--pending-stale-after-seconds", type=int, default=86400)
    parser.add_argument("--strict", action="store_true", help="treat warnings (orphan candidates, stale PENDING...) as failures")
    parser.add_argument("--json", action="store_true")
    return parser


async def run(
    argv: list[str],
    *,
    settings: Settings,
    session_factory: Callable[[], Any],
    storage_factory: Callable[[Settings], MediaStorageAdmin],
    out=sys.stdout,
) -> int:
    args = build_parser().parse_args(argv)
    if settings.MEDIA_STORAGE_BACKEND == "disabled":
        print(
            "Media integrity check cannot run: MEDIA_STORAGE_BACKEND=disabled. "
            "Storage state is unknown (not assumed empty).",
            file=out,
        )
        return EXIT_CANNOT_RUN
    storage_name = args.expect_storage_name or settings.MEDIA_STORAGE_NAME
    storage = storage_factory(settings)

    session: AsyncSession
    async with session_factory() as session:
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            await session.execute(text("SET TRANSACTION READ ONLY"))
        try:
            assets = await PhotoAssetService(session).list_for_integrity()
        finally:
            await session.rollback()

    try:
        report = await run_integrity_check(
            assets,
            storage,
            storage_name=storage_name,
            temp_dir=settings.PHOTO_TEMP_DIR,
            verify_sha256=args.verify_sha256,
            pending_stale_after_seconds=args.pending_stale_after_seconds,
        )
    except MediaStorageError as exc:
        print(
            f"Media integrity check aborted: {type(exc).__name__}"
            f" (code={exc.error_code}, status={exc.http_status}). Result is incomplete.",
            file=out,
        )
        return EXIT_CANNOT_RUN

    if args.json:
        print(
            json.dumps(
                {
                    "storage_name": report.storage_name,
                    "checked_assets": dict(report.checked_assets),
                    "expected_present": report.expected_present,
                    "checksum_verified": report.checksum_verified,
                    "findings": [asdict(f) for f in report.findings],
                    "errors": len(report.errors),
                    "warnings": len(report.warnings),
                },
                indent=2,
            ),
            file=out,
        )
    else:
        print(format_report(report), file=out)
    return report.exit_code(strict=args.strict)


def main() -> None:
    from app.core.config import settings
    from app.core.database import async_session_maker
    from app.core.s3_media_storage import create_media_storage

    sys.exit(
        asyncio.run(
            run(
                sys.argv[1:],
                settings=settings,
                session_factory=async_session_maker,
                storage_factory=create_media_storage,  # type: ignore[arg-type]
            )
        )
    )


if __name__ == "__main__":
    main()
