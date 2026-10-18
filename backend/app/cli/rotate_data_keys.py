"""`python -m app.cli.rotate_data_keys` -- the change of the data key of an owner (EN-3b). Counts only, never a key or a value.

    status                              read only: per owner, the data keys and how many values each still seals
    start  --owner ID | --all           make a NEW active data key (the old one stays, inactive); then recreate the backend, then `reseal`
    reseal [--owner ID] [--batch-size N] [--limit N]
                                        seal with the active key every value that another key seals (repeatable and resumable)
    retire [--owner ID]                 delete the inactive data keys that no value is sealed with (refuses if any still is)

Run inside the backend container: `docker exec plan_estimate_backend python -m app.cli.rotate_data_keys status`.
Exit codes: 0 done, 2 usage, 3 some value is still sealed with an old key / undecryptable / skipped, 4 DATA_KEK missing, 6 refused (nothing changed).
"""
import argparse
import asyncio
import sys
import uuid

from app.core.data_crypto import DataCryptoError, DataKeyConfigurationError
from app.core.database import async_session_maker
from app.domain.services.dek_rotation_service import (
    DataKeyRotationRefusedError,
    DekRotationService,
    OwnerKeys,
)

EXIT_OK, EXIT_REMAINS, EXIT_NO_KEY, EXIT_REFUSED = 0, 3, 4, 6


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli.rotate_data_keys")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    start = commands.add_parser("start")
    group = start.add_mutually_exclusive_group(required=True)
    group.add_argument("--owner", type=uuid.UUID)
    group.add_argument("--all", action="store_true")
    reseal = commands.add_parser("reseal")
    reseal.add_argument("--owner", type=uuid.UUID)
    reseal.add_argument("--batch-size", type=int, default=200)
    reseal.add_argument("--limit", type=int, default=None)
    retire = commands.add_parser("retire")
    retire.add_argument("--owner", type=uuid.UUID)
    return parser


def render(owners: list[OwnerKeys], out) -> None:
    for owner in owners:
        print(f"owner {str(owner.owner_id)[:8]}:", file=out)
        for key in owner.keys:
            print(f"  key {key.key_id[:8]} {'ACTIVE' if key.active else 'inactive'}: seals {key.values} value(s)", file=out)
    pending = sum(owner.to_reseal for owner in owners)
    print(f"STILL SEALED WITH AN OLD KEY: {pending}", file=out)


async def run(argv: list[str], out=sys.stdout) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "reseal" and (args.batch_size < 1 or (args.limit is not None and args.limit < 1)):
        print("usage: --batch-size and --limit must be positive", file=out)
        return 2
    service = DekRotationService(async_session_maker, batch_size=getattr(args, "batch_size", 200))
    try:
        if args.command == "start":
            owners = [args.owner] if args.owner else [owner.owner_id for owner in await service.status()]
            for owner_id in owners:
                new_id = await service.start(owner_id)
                print(f"owner {str(owner_id)[:8]}: new active data key {new_id[:8]}", file=out)
            print("NEXT: recreate the backend (it holds the old key in memory), then run reseal", file=out)
            return EXIT_OK
        if args.command == "reseal":
            stats = await service.reseal(args.owner, args.limit)
            print(f"resealed {stats.resealed}; skipped because changed {stats.skipped_changed}; undecryptable {stats.undecryptable}", file=out)
            owners = [o for o in await service.status() if args.owner is None or o.owner_id == args.owner]
            render(owners, out)
            if stats.undecryptable or stats.skipped_changed:
                return EXIT_REMAINS
            return EXIT_OK if args.limit is not None or all(owner.done for owner in owners) else EXIT_REMAINS  # a limited run may leave the rest
        if args.command == "retire":
            print(f"deleted {await service.retire(args.owner)} inactive data key(s)", file=out)
            return EXIT_OK
        owners = await service.status()
    except DataKeyRotationRefusedError as error:
        print(f"refused, nothing changed: {error}", file=out)
        return EXIT_REFUSED
    except DataKeyConfigurationError as error:
        print(f"nothing done: {error}", file=out)
        return EXIT_NO_KEY
    except DataCryptoError as error:
        print(f"stopped: {error.code}", file=out)
        return EXIT_REMAINS
    render(owners, out)
    return EXIT_OK if all(owner.done for owner in owners) else EXIT_REMAINS


def main() -> None:
    sys.exit(asyncio.run(run(sys.argv[1:])))


if __name__ == "__main__":
    main()
