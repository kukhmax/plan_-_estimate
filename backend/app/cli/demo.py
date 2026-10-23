"""`python -m app.cli.demo` -- demo data of one account (V2-2; docs/V2_2_PLAN_RU.md).

    seed   (--email E | --telegram-id N) [--no-prices]    the demo client, the object "DEMO · Mieszkanie 50 m²" with five rooms and walls,
                                                          and demo prices for the price rows that have no price yet
    remove (--email E | --telegram-id N) [--keep-prices]  the demo object and client are deleted for good; the prices that still equal
                                                          the demo values go back to "to be agreed"
    status (--email E | --telegram-id N)                  what of the demo data the account has

Run inside the backend container: `docker exec plan_estimate_backend python -m app.cli.demo seed --email jan@example.pl`.
Nothing is created until this command is run. Exit codes: 0 done, 1 refused (the reason is printed), 2 usage.
"""
import argparse
import asyncio
import sys

from sqlalchemy import select

from app.api.deps import get_media_purger
from app.core.database import async_session_maker
from app.domain.exceptions import (
    ClientHasProjectsError,
    ProjectNotArchivedError,
    ProjectPurgeBlockedError,
    ProjectPurgeConflictError,
)
from app.domain.services.demo_data_service import DemoDataService
from app.domain.services.password_login_service import normalize_email
from app.models.user import User
from app.models.user_credential import UserCredential

EXIT_OK, EXIT_REFUSED = 0, 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli.demo")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("seed", "remove", "status"):
        command = commands.add_parser(name)
        who = command.add_mutually_exclusive_group(required=True)
        who.add_argument("--email")
        who.add_argument("--telegram-id", type=int)
        if name == "seed":
            command.add_argument("--no-prices", action="store_true")
        if name == "remove":
            command.add_argument("--keep-prices", action="store_true")
    return parser


async def _find_user(session, args) -> User | None:
    if args.email:
        stmt = select(User).join(UserCredential, UserCredential.user_id == User.id).where(UserCredential.email == normalize_email(args.email))
    else:
        stmt = select(User).where(User.telegram_user_id == args.telegram_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def run(argv: list[str], out=sys.stdout) -> int:
    args = build_parser().parse_args(argv)
    async with async_session_maker() as session:
        user = await _find_user(session, args)
        if user is None:
            print("refused: ACCOUNT_NOT_FOUND -- no such account", file=out)
            return EXIT_REFUSED
        service = DemoDataService(session, get_media_purger())
        try:
            if args.command == "status":
                status = await service.status(user.id)
                print(f"demo object: {status.project_id or 'none'}  rooms: {status.rooms}  demo client: {status.client_id or 'none'}  "
                      f"prices equal to the demo values: {status.demo_priced_items}", file=out)
            elif args.command == "seed":
                result = await service.seed(user.id, with_prices=not args.no_prices)
                print(f"demo object: {'created' if result.created_objects else 'already there'} ({result.rooms} rooms made); prices set: {result.priced_items}", file=out)
            else:
                result = await service.remove(user.id, reset_prices=not args.keep_prices)
                print(f"demo object removed: {result.removed_project}; demo client removed: {result.removed_client}; prices reset: {result.prices_reset}", file=out)
                if result.client_kept_reason:
                    print(f"note: the demo client stays ({result.client_kept_reason})", file=out)
        except (ProjectPurgeBlockedError, ProjectPurgeConflictError, ProjectNotArchivedError, ClientHasProjectsError) as error:
            print(f"refused: {getattr(error, 'code', type(error).__name__)} -- {error}", file=out)
            return EXIT_REFUSED
    return EXIT_OK


def main() -> None:
    sys.exit(asyncio.run(run(sys.argv[1:])))


if __name__ == "__main__":
    main()
