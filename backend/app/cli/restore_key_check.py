"""`python -m app.cli.restore_key_check [--allow-plain]` -- can a RESTORED backup be read with the saved key? (EN-3c). Read only; counts and fingerprints only.

Run it against a database restored into a SCRATCH PostgreSQL (docs/CLIENT_ENCRYPTION_RESTORE_REHEARSAL_RU.md): `DATABASE_URL` names it (the name must contain
`pe_restore_scratch`, the host must be loopback or contain `scratch`), `DATA_KEK` is the SAVED COPY of the key of the server (from the password manager, not the
server's file), and `DATA_KEK_PREVIOUS` the old key for a backup made before a rotation of the key. `--allow-plain` accepts plain values (a backup made before
the re-encoding of EN-2b). Exit codes: 0 PASS, 2 refused (not a scratch database / usage), 3 FAIL (the reasons are printed), 4 DATA_KEK missing or invalid.
"""
import argparse
import asyncio
import sys

from app.core.config import settings
from app.core.data_crypto import DataCryptoError, DataKeyConfigurationError
from app.core.database import async_session_maker
from app.domain.services.restore_key_check_service import (
    RestoreKeyCheckService,
    RestoreKeyReport,
    UnsafeRestoreCheckTargetError,
    key_fingerprints,
    validate_scratch_url,
)

EXIT_PASS, EXIT_REFUSED, EXIT_FAIL, EXIT_NO_KEY = 0, 2, 3, 4


def render(report: RestoreKeyReport, out) -> None:
    current, previous = key_fingerprints()
    match = "MATCHES the code" if report.revision and report.revision == report.code_head else "DIFFERS from the code"
    print(f"alembic revision of the restored database: {report.revision or '-'} (code head: {report.code_head or '-'}) -- {match}", file=out)
    print(f"key of the server supplied: fingerprint {current}; previous key: {previous or 'none'}", file=out)
    keys = report.keys
    print(f"data keys: {keys.total} (open with DATA_KEK alone: {keys.current}; only with DATA_KEK_PREVIOUS: {keys.previous_only}; open with neither: {keys.unreadable})", file=out)
    if report.wrong_key_opens is not None:
        print(f"a random wrong key opens a data key: {'YES (not expected!)' if report.wrong_key_opens else 'no (expected)'}", file=out)
    print(f"values: ciphertext {report.ciphertext}, plain {report.plain}{' (allowed)' if report.allow_plain and report.plain else ''}, do not decrypt {report.undecryptable}", file=out)
    if keys.previous_only:
        print("NOTE: some data keys open only with the PREVIOUS key: this backup was made before a rotation of the key of the server; keep the old key.", file=out)
    print("RESTORE KEY CHECK: PASS" if report.passed else "RESTORE KEY CHECK: FAIL (" + ", ".join(report.reasons) + ")", file=out)


async def run(argv: list[str], out=sys.stdout) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli.restore_key_check")
    parser.add_argument("--allow-plain", action="store_true")
    args = parser.parse_args(argv)
    try:
        validate_scratch_url(settings.DATABASE_URL)
    except UnsafeRestoreCheckTargetError as error:
        print(f"refused, nothing was opened: {error}", file=out)
        return EXIT_REFUSED
    try:
        report = await RestoreKeyCheckService(async_session_maker).run(allow_plain=args.allow_plain)
    except DataKeyConfigurationError as error:
        print(f"nothing done: {error}", file=out)
        return EXIT_NO_KEY
    except DataCryptoError as error:
        print(f"stopped: {error.code}", file=out)
        return EXIT_FAIL
    render(report, out)
    return EXIT_PASS if report.passed else EXIT_FAIL


def main() -> None:
    sys.exit(asyncio.run(run(sys.argv[1:])))


if __name__ == "__main__":
    main()
