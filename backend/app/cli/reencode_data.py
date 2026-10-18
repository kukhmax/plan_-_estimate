"""`python -m app.cli.reencode_data` -- the re-encoding of the plain values of the encrypted columns (EN-2b-1).

    report [--batch-size N]            read only: per column, how many values are stored and how many are still plain
    verify [--batch-size N]            read only: report + every ciphertext is decrypted (a wrong key, a damaged or moved value is counted)
    apply  [--batch-size N] [--limit N] turn the plain values into ciphertext (repeatable and resumable); prints the same table afterwards

Run inside the backend container: `docker exec plan_estimate_backend python -m app.cli.reencode_data report`.
It prints counts only, never a value or a key. Exit codes: 0 done and nothing plain / undecryptable is left (report: always 0), 2 usage,
3 plain or undecryptable values remain after `verify` / `apply`, 4 the key of the server is not configured, 5 a value was skipped because it changed.
"""
import argparse
import asyncio
import sys

from app.core.data_crypto import DataCryptoError, DataKeyConfigurationError
from app.core.database import async_session_maker
from app.domain.services.data_reencode_service import ColumnStats, DataReencodeService

EXIT_OK, EXIT_REMAINS, EXIT_NO_KEY, EXIT_SKIPPED = 0, 3, 4, 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli.reencode_data")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("report", "verify", "apply"):
        command = commands.add_parser(name)
        command.add_argument("--batch-size", type=int, default=200)
        if name == "apply":
            command.add_argument("--limit", type=int, default=None, help="at most this many values in this run")
    return parser


def render(stats: list[ColumnStats], out, converted: bool, verified: bool) -> None:
    head = f"{'table.column':42} {'stored':>7} {'ciphertext':>10} {'plain':>6}" + (f" {'converted':>9} {'changed':>7}" if converted else "") + (f" {'undecrypt':>9}" if verified else "")
    print(head, file=out)
    for s in stats:
        line = f"{s.table + '.' + s.column:42} {s.non_null:>7} {s.encrypted:>10} {s.plain:>6}"
        if converted:
            line += f" {s.converted:>9} {s.skipped_changed:>7}"
        if verified:
            line += f" {s.undecryptable:>9}"
        print(line, file=out)
    print(f"TOTAL plain={sum(s.plain for s in stats)} ciphertext={sum(s.encrypted for s in stats)} undecryptable={sum(s.undecryptable for s in stats)}", file=out)


async def run(argv: list[str], out=sys.stdout) -> int:
    args = build_parser().parse_args(argv)
    if args.batch_size < 1 or (args.command == "apply" and args.limit is not None and args.limit < 1):
        print("usage: --batch-size and --limit must be positive", file=out)
        return 2
    service = DataReencodeService(async_session_maker, batch_size=args.batch_size)
    try:
        if args.command == "apply":
            stats = await service.apply(limit=args.limit)
        else:
            stats = await service.count(verify=args.command == "verify")
    except DataKeyConfigurationError:
        print("the key of the server (DATA_KEK) is not configured: nothing to do", file=out)
        return EXIT_NO_KEY
    except DataCryptoError as error:
        print(f"stopped: {error.code}", file=out)
        return EXIT_REMAINS
    render(stats, out, converted=args.command == "apply", verified=args.command == "verify")
    if args.command == "report":
        return EXIT_OK
    if any(s.undecryptable for s in stats) or (args.command == "verify" and any(s.plain for s in stats)):
        return EXIT_REMAINS
    if args.command == "apply":
        if any(s.skipped_changed for s in stats):
            return EXIT_SKIPPED
        if args.limit is None and any(s.plain for s in stats):
            return EXIT_REMAINS
    return EXIT_OK


def main() -> None:
    sys.exit(asyncio.run(run(sys.argv[1:])))


if __name__ == "__main__":
    main()
