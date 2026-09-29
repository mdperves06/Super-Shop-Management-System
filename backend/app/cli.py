"""Operational commands.

    python -m app.cli migrate                      # apply Alembic migrations + reference data (idempotent)
    python -m app.cli create-superadmin --email owner@shop.com --name "Shop Owner"
                                                   # prompts for the password (or use ADMIN_PASSWORD env)
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import select


def cmd_migrate() -> None:
    from alembic.config import Config

    from alembic import command
    from app.core.config import BASE_DIR
    from app.core.database import SessionLocal
    from app.services.bootstrap import ensure_reference_data

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    command.upgrade(cfg, "head")
    with SessionLocal() as db:
        ensure_reference_data(db)
        db.commit()
    print("Database is up to date.")


def cmd_create_superadmin(email: str, name: str, password: str | None) -> None:
    from app.core.database import SessionLocal
    from app.core.rbac import SUPER_ADMIN
    from app.models.auth import Role
    from app.schemas.auth import _check_password
    from app.services import auth_service
    from app.services.bootstrap import ensure_reference_data

    password = password or os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password: ")
    try:
        _check_password(password)
    except ValueError as exc:
        sys.exit(f"Weak password: {exc}")
    with SessionLocal() as db:
        ensure_reference_data(db)
        role = db.scalar(select(Role).where(Role.name == SUPER_ADMIN))
        user = auth_service.create_user(db, email=email, full_name=name, password=password, role_ids=[role.id])
        db.commit()
        print(f"Created Super Admin {user.email}. Sign in and enable two-factor authentication under My profile.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    p = sub.add_parser("create-superadmin")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--password", help="avoid on shared machines; prefer the prompt or ADMIN_PASSWORD")
    args = parser.parse_args()
    if args.command == "migrate":
        cmd_migrate()
    else:
        cmd_create_superadmin(args.email, args.name, args.password)


if __name__ == "__main__":
    main()
