"""`python -m app.cli.users` -- the accounts that sign in with an e-mail and a password (V2-1; docs/V2_1_PLAN_RU.md).

    create --email E --name N [--password-stdin]   a new account; the password is made here and printed ONCE (or read from the standard input)
    set-password --email E [--password-stdin]      a new password for an account (clears a lock)
    list                                           the e-mails, names and last sign-ins (no passwords)

Run inside the backend container: `docker exec -i plan_estimate_backend python -m app.cli.users create --email jan@example.pl --name "Jan"`.
The sign-in itself works only when AUTH_PASSWORD_ENABLED is true. Exit codes: 0 done, 1 refused (the reason is printed), 2 usage.
"""
import argparse
import asyncio
import sys

from app.core.database import async_session_maker
from app.domain.exceptions import WebAccountError
from app.domain.services.password_login_service import PasswordLoginService

EXIT_OK, EXIT_REFUSED = 0, 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli.users")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--email", required=True)
    create.add_argument("--name", default="")
    create.add_argument("--password-stdin", action="store_true")
    change = commands.add_parser("set-password")
    change.add_argument("--email", required=True)
    change.add_argument("--password-stdin", action="store_true")
    commands.add_parser("list")
    return parser


async def run(argv: list[str], out=sys.stdout, stdin=sys.stdin) -> int:
    args = build_parser().parse_args(argv)
    async with async_session_maker() as session:
        service = PasswordLoginService(session)
        try:
            if args.command == "list":
                for email, name, last in await service.list_accounts():
                    print(f"{email}\t{name or '-'}\t{last.isoformat() if last else 'never signed in'}", file=out)
                return EXIT_OK
            typed = stdin.readline().rstrip("\n") if args.password_stdin else None
            if args.command == "create":
                _, password = await service.create_account(args.email, args.name, typed)
                print(f"account made: {args.email.strip().lower()}", file=out)
            else:
                password = await service.set_password(args.email, typed)
                print(f"password changed: {args.email.strip().lower()}", file=out)
            if typed is None:
                print(f"password (shown once, keep it in the password manager): {password}", file=out)
        except WebAccountError as error:
            print(f"refused: {error.code} -- {error.message}", file=out)
            return EXIT_REFUSED
    return EXIT_OK


def main() -> None:
    sys.exit(asyncio.run(run(sys.argv[1:])))


if __name__ == "__main__":
    main()
