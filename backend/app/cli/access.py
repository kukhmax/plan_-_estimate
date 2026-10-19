"""`python -m app.cli.access` -- the access list from the command line (closed registration). The recovery tool: it does not need the screen.

    status                       read only: is the registration closed; how many accounts are ACTIVE / PENDING / BLOCKED; how many administrators
    set-admin --telegram-id N    make this Telegram account the only administrator (it is admitted if it was not)
    open                         anyone may register again (the list is kept)
    close                        only the ACTIVE accounts enter

Run inside the backend container: `docker exec plan_estimate_backend python -m app.cli.access status`.
Prints counts only (no names). Exit codes: 0 done, 2 usage.
"""
import argparse
import asyncio
import sys

from sqlalchemy import func, select

from app.core.database import async_session_maker
from app.domain.services.access_service import AccessService
from app.models.access_entry import AccessEntry

EXIT_OK = 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli.access")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "open", "close"):
        commands.add_parser(name)
    admin = commands.add_parser("set-admin")
    admin.add_argument("--telegram-id", type=int, required=True)
    return parser


async def render(session, out) -> None:
    service = AccessService(session)
    counts = dict((await session.execute(select(AccessEntry.status, func.count()).group_by(AccessEntry.status))).all())
    admins = (await session.execute(select(func.count()).select_from(AccessEntry).where(AccessEntry.is_admin.is_(True)))).scalar_one()
    print(f"registration: {'CLOSED (only ACTIVE accounts enter)' if await service.is_closed() else 'OPEN (anyone may register)'}", file=out)
    print(f"  ACTIVE: {counts.get('ACTIVE', 0)}  PENDING: {counts.get('PENDING', 0)}  BLOCKED: {counts.get('BLOCKED', 0)}  administrators: {admins}", file=out)


async def run(argv: list[str], out=sys.stdout) -> int:
    args = build_parser().parse_args(argv)
    async with async_session_maker() as session:
        service = AccessService(session)
        if args.command == "set-admin":
            await service.set_admin(args.telegram_id)
        elif args.command in ("open", "close"):
            await service.set_closed(args.command == "close")
        await render(session, out)
    return EXIT_OK


def main() -> None:
    sys.exit(asyncio.run(run(sys.argv[1:])))


if __name__ == "__main__":
    main()
