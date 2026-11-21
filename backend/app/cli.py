"""Admin CLI: `python -m app.cli <command>`. The only way to create accounts (no public signup).

Passwords are always read with getpass (no echo), never from arguments, and never printed.
"""

import argparse
import getpass
import sys
import uuid
from collections.abc import Sequence

from app.composition import build_container, build_user_service, run_migrations
from app.domain.errors import (
    DataAccessError,
    DomainError,
    EnrichAlreadyRunning,
    ItemNotFound,
    LibraryUnavailable,
    MetadataDisabled,
    ScanAlreadyRunning,
)
from app.domain.user import Role, User, UserError
from app.services.user_service import UserService


def _prompt_password() -> str | None:
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        print("error: passwords do not match", file=sys.stderr)
        return None
    return first


def _cmd_create_user(service: UserService, args: argparse.Namespace) -> int:
    password = _prompt_password()
    if password is None:
        return 1
    role = Role.ADMIN if args.admin else Role.USER
    user = service.create_user(args.username, password, role=role)
    print(f"created {user.role.value} '{user.username}'")
    return 0


def _cmd_reset_password(service: UserService, args: argparse.Namespace) -> int:
    password = _prompt_password()
    if password is None:
        return 1
    user = service.reset_password(args.username, password)
    print(f"password reset for '{user.username}'")
    return 0


def _cmd_deactivate_user(service: UserService, args: argparse.Namespace) -> int:
    user = service.deactivate_user(args.username)
    print(f"deactivated '{user.username}'")
    return 0


def _format_user(user: User) -> str:
    state = "active" if user.is_active else "inactive"
    return f"{user.username}\t{user.role.value}\t{state}"


def _cmd_list_users(service: UserService, _args: argparse.Namespace) -> int:
    for user in service.list_users():
        print(_format_user(user))
    return 0


def _cmd_scan() -> int:
    """Scan the configured library (LIBRARY_PATH) in this process. Prints counts only."""
    try:
        status = build_container().scan_runner.run()
    except LibraryUnavailable:
        print("error: library folder is not available (check LIBRARY_PATH)", file=sys.stderr)
        return 1
    except ScanAlreadyRunning:
        print("error: a scan is already running", file=sys.stderr)
        return 1
    print(
        f"scan {status.state.value}: added={status.added} updated={status.updated} "
        f"unchanged={status.unchanged} removed={status.removed} skipped={status.skipped} "
        f"errors={status.error_count}"
    )
    for reason, count in sorted(status.errors_by_reason.items()):
        print(f"  {reason}: {count}")
    return 0 if status.state.value == "finished" else 1


def _cmd_enrich(args: argparse.Namespace) -> int:
    """Fetch covers/descriptions from the public sources (METADATA_ENABLED must be true)."""
    series_id: str | None = None
    if args.series is not None:
        try:
            series_id = str(uuid.UUID(args.series))
        except ValueError:
            print("error: --series must be a series id (UUID)", file=sys.stderr)
            return 1
    container = build_container()
    try:
        container.metadata_service.require_enabled()
        if series_id is not None and container.series_repository.get(series_id) is None:
            raise ItemNotFound
        status = container.enrich_runner.run(force=args.force, series_id=series_id)
    except MetadataDisabled:
        print("error: metadata lookup is disabled (METADATA_ENABLED=false)", file=sys.stderr)
        return 1
    except ItemNotFound:
        print("error: series not found", file=sys.stderr)
        return 1
    except EnrichAlreadyRunning:
        print("error: an enrichment is already running", file=sys.stderr)
        return 1
    print(
        f"enrich {status.state.value}: matched={status.matched} not_found={status.not_found} "
        f"skipped={status.skipped} errors={status.errors}"
    )
    return 0 if status.state.value == "finished" else 1


def _cmd_purge() -> int:
    """Delete expired login attempts, dead sessions and audit events past retention."""
    attempts, families, events = build_container().auth_service.purge_expired()
    print(f"purge done: login_attempts={attempts} dead_sessions={families} audit_events={events}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Reader admin CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-user", help="create an account (password via prompt)")
    create.add_argument("username")
    create.add_argument("--admin", action="store_true", help="create with the admin role")
    reset = sub.add_parser("reset-password", help="set a new password (via prompt)")
    reset.add_argument("username")
    deactivate = sub.add_parser("deactivate-user", help="disable an account")
    deactivate.add_argument("username")
    sub.add_parser("list-users", help="list accounts")
    sub.add_parser("scan", help="scan the library folder (LIBRARY_PATH) and update the catalog")
    enrich = sub.add_parser(
        "enrich", help="fetch covers and descriptions from public sources (see METADATA_*)"
    )
    enrich.add_argument("--series", help="only this series id (UUID)")
    enrich.add_argument(
        "--force", action="store_true", help="re-check matched/not_found series (never manual)"
    )
    sub.add_parser("migrate", help="apply database migrations (alembic upgrade head)")
    sub.add_parser("purge", help="delete expired login attempts, dead sessions and old audit rows")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "migrate":
            run_migrations()
            print("database is up to date")
            return 0
        if args.command == "scan":
            return _cmd_scan()
        if args.command == "enrich":
            return _cmd_enrich(args)
        if args.command == "purge":
            return _cmd_purge()
        service = build_user_service()
        handlers = {
            "create-user": _cmd_create_user,
            "reset-password": _cmd_reset_password,
            "deactivate-user": _cmd_deactivate_user,
            "list-users": _cmd_list_users,
        }
        return handlers[args.command](service, args)
    except DataAccessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("hint: did you run `python -m app.cli migrate`?", file=sys.stderr)
        return 1
    except DomainError as exc:
        print(f"error: {type(exc).__name__}", file=sys.stderr)
        return 1
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
