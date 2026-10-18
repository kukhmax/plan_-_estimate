"""`python -m app.cli.rotate_keys` -- the rotation of the key of the server (EN-3a). Counts only, never a key or a value.

    new-key   prints a fresh DATA_KEK (base64 of 32 random bytes): copy it to the password manager BEFORE anything else; nothing is stored
    status    read only: how many data keys open with the current key alone / only with the previous key / with neither
    rewrap    re-wrap every data key that opens only with DATA_KEK_PREVIOUS with DATA_KEK (all or nothing); prints the status afterwards
    verify    read only: every data key opens with DATA_KEK ALONE (exit 0): DATA_KEK_PREVIOUS may be removed

Run inside the backend container: `docker exec plan_estimate_backend python -m app.cli.rotate_keys status`.
Exit codes: 0 done / nothing to do, 2 usage, 3 some key is unreadable or still wrapped by the old key, 4 DATA_KEK missing / invalid / the same as the previous one.
"""
import argparse
import asyncio
import sys

from app.core.config import settings
from app.core.data_crypto import DataCryptoError, DataKeyConfigurationError
from app.core.database import async_session_maker
from app.domain.services.kek_rotation_service import KekRotationService, KekStatus

EXIT_OK, EXIT_REMAINS, EXIT_NO_KEY = 0, 3, 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli.rotate_keys")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("new-key", "status", "rewrap", "verify"):
        commands.add_parser(name)
    return parser


def render(status: KekStatus, out) -> None:
    versions = ", ".join(f"v{version}: {count}" for version, count in sorted(status.versions.items())) or "-"
    print(f"data keys wrapped by the key of the server: {status.total} (by version: {versions}); wrapped by a key of an owner: {status.owner_wrapped}", file=out)
    print(f"  open with DATA_KEK (version {settings.DATA_KEK_VERSION}) alone: {status.current}", file=out)
    print(f"  open only with DATA_KEK_PREVIOUS (still to be re-wrapped): {status.previous_only}", file=out)
    print(f"  open with neither (unreadable): {status.unreadable}", file=out)
    if status.rewrapped:
        print(f"  re-wrapped in this run: {status.rewrapped}", file=out)
    print(f"ROTATION {'DONE' if status.done else 'NOT DONE'}", file=out)


async def run(argv: list[str], out=sys.stdout) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "new-key":
        print(KekRotationService.new_kek_text(), file=out)
        return EXIT_OK
    service = KekRotationService(async_session_maker)
    try:
        status = await (service.rewrap() if args.command == "rewrap" else service.status())
    except DataKeyConfigurationError as error:
        print(f"nothing done: {error}", file=out)
        return EXIT_NO_KEY
    except DataCryptoError as error:
        print(f"stopped: {error.code}", file=out)
        return EXIT_REMAINS
    render(status, out)
    ok = not status.unreadable if args.command == "status" else status.done  # rewrap / verify: every key opens with the current key alone
    return EXIT_OK if ok else EXIT_REMAINS


def main() -> None:
    sys.exit(asyncio.run(run(sys.argv[1:])))


if __name__ == "__main__":
    main()
