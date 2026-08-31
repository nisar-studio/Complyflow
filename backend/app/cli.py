"""
ComplyFlow — Command-Line Interface

Provides administrative utilities for production deployments:
  - create-admin: provision the initial ADMIN user in production
  - add-member: add a user to a project with a role
  - verify-config: validate production configuration
  - migrate: run pending database migrations
  - migrate-status: show migration status

Usage:
  python -m app create-admin
  python -m app create-admin --email admin@example.com --name "Admin User"
  python -m app verify-config
  python -m app migrate
  python -m app migrate-status
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys


def _setup_env():
    """Ensure the backend app package is importable."""
    app_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(app_dir)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)


def _create_admin(args):
    """Create the initial ADMIN user for production deployment."""
    _setup_env()
    from app.core.config import get_settings, Settings
    from app.services.storage import get_storage
    from app.services.auth_service import hash_password, Role
    import secrets

    settings = get_settings()

    # Warn if not production (but allow it for testing)
    if not settings.is_production():
        print("WARNING: Running in non-production mode. For production, set APP_ENV=production.")
        print("")

    # Collect email
    email = args.email
    if not email:
        email = input("Admin email: ").strip()
    if not email or "@" not in email:
        print("ERROR: Invalid email address.")
        sys.exit(1)

    # Collect name
    name = args.name
    if not name:
        name = input("Admin name [Compliance Admin]: ").strip() or "Compliance Admin"

    # Collect password securely
    password = args.password
    if not password:
        password = getpass.getpass("Admin password: ")
        if not password:
            print("ERROR: Password cannot be empty.")
            sys.exit(1)
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("ERROR: Passwords do not match.")
            sys.exit(1)

    # Validate password strength
    if len(password) < 8:
        print("ERROR: Password must be at least 8 characters.")
        sys.exit(1)

    async def _create():
        storage = get_storage()
        # Ensure DB schema exists
        await storage._init_db()

        # Check if user already exists
        existing = await storage.get_user_by_email(email)
        if existing:
            print(f"NOTE: User '{email}' already exists (ID: {existing['user_id']}).")
            print("   Skipping creation. To create a different admin, use a different email.")
            return existing

        user_id = f"user_admin_{secrets.token_hex(4)}"
        pw_hash = hash_password(password)
        user_data = {
            "user_id": user_id,
            "email": email,
            "name": name,
            "password_hash": pw_hash,
            "is_active": True,
        }
        await storage.create_user(user_data)

        print("")
        print("SUCCESS: Admin user created successfully.")
        print(f"   User ID:  {user_id}")
        print(f"   Email:    {email}")
        print(f"   Name:     {name}")
        print(f"   Role:     ADMIN")
        print("")
        print("IMPORTANT: Save this information. The password cannot be recovered.")
        print("   Log in via the ComplyFlow UI to start using the application.")

        return {"user_id": user_id, "email": email, "name": name}

    asyncio.run(_create())


def _create_admin_project_membership(args):
    """Add the admin user to a project as ADMIN (for testing/development)."""
    _setup_env()
    from app.core.config import get_settings
    from app.services.storage import get_storage
    from app.services.auth_service import Role

    async def _add():
        storage = get_storage()
        await storage._init_db()

        email = args.email
        if not email:
            email = input("Admin email: ").strip()

        user = await storage.get_user_by_email(email)
        if not user:
            print(f"ERROR: User '{email}' not found. Create them first with: python -m app create-admin")
            sys.exit(1)

        project_id = args.project_id
        if not project_id:
            project_id = input("Project ID: ").strip()

        project = await storage.get_project(project_id)
        if not project:
            print(f"ERROR: Project '{project_id}' not found.")
            sys.exit(1)

        role = args.role or "ADMIN"
        if not role.upper() in Role.all_roles():
            print(f"ERROR: Invalid role '{role}'. Must be one of: {', '.join(Role.all_roles())}")
            sys.exit(1)

        await storage.add_project_member(project_id, user["user_id"], role.upper())
        print(f"SUCCESS: Added '{email}' to project '{project_id}' as {role.upper()}.")

    asyncio.run(_add())


def _verify_config(args):
    """Validate production configuration."""
    _setup_env()
    from app.core.config import Settings

    settings = Settings()

    print(f"Environment: {settings.app_env}")
    print(f"Production:  {settings.is_production()}")
    print("")

    if settings.is_production():
        print("Running production validation...")
        try:
            warnings = settings.validate_production_settings()
            print("OK: All critical settings pass.")
            if warnings:
                print("")
                print("Warnings:")
                for w in warnings:
                    print(f"   - {w}")
            else:
                print("   No warnings.")
        except ValueError as exc:
            print(f"CRITICAL: {exc}")
            sys.exit(1)
    else:
        print("INFO: Not in production mode. Skipping production validation.")
        print("   Set APP_ENV=production to validate production settings.")

    print("")
    print("Configuration summary:")
    print(f"   Database:        {settings.database_path}")
    print(f"   Upload dir:      {settings.upload_dir}")
    print(f"   Backend:         {settings.backend_host}:{settings.backend_port}")
    print(f"   CORS origins:    {settings.cors_origins}")
    print(f"   Cookie secure:   {settings.cookie_secure}")
    print(f"   Session secret:  {'[SET]' if settings.session_secret else '[NOT SET]'}")
    print(f"   CSRF secret:     {'[SET]' if settings.csrf_secret else '[NOT SET]'}")
    print(f"   Gemini model:    {settings.gemini_model}")
    print(f"   Gemini key:      {'[SET]' if settings.gemini_api_key else '[NOT SET]'}")


def _migrate(args):
    """Run pending database migrations."""
    _setup_env()
    from app.core.config import get_settings
    from app.services.migration_service import run_pending_migrations

    settings = get_settings()
    db_path = settings.database_path

    print(f"Database: {db_path}")
    print("Running pending migrations...")
    print("")

    async def _run():
        applied = await run_pending_migrations(db_path)
        return applied

    applied = asyncio.run(_run())

    if applied:
        print(f"Applied {len(applied)} migration(s):")
        for mid in applied:
            print(f"   ✓ {mid}")
    else:
        print("No pending migrations. Database is up to date.")

    print("")
    print("Migration complete.")


def _migrate_status(args):
    """Show migration status."""
    _setup_env()
    from app.core.config import get_settings
    from app.services.migration_service import get_migration_status

    settings = get_settings()
    db_path = settings.database_path

    print(f"Database: {db_path}")
    print("")

    async def _status():
        return await get_migration_status(db_path)

    status = asyncio.run(_status())

    print(f"Total migrations:  {status['total']}")
    print(f"Applied:           {status['applied_count']}")
    print(f"Pending:           {status['pending_count']}")
    print("")

    if status["applied"]:
        print("Applied migrations:")
        for m in status["applied"]:
            print(f"   ✓ {m['id']} — {m['name']} (applied: {m['applied_at'][:19]})")
        print("")

    if status["pending"]:
        print("Pending migrations:")
        for m in status["pending"]:
            print(f"   ○ {m['id']} — {m['name']}")
        print("")
    else:
        print("All migrations applied. Database is up to date.")


def main():
    parser = argparse.ArgumentParser(
        prog="complyflow",
        description="ComplyFlow — Administrative CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # create-admin
    admin_parser = subparsers.add_parser("create-admin", help="Create the initial ADMIN user")
    admin_parser.add_argument("--email", help="Admin email address")
    admin_parser.add_argument("--name", help="Admin display name", default=None)
    admin_parser.add_argument("--password", help="Admin password (prefer interactive prompt for security)")
    admin_parser.set_defaults(func=_create_admin)

    # add-member
    member_parser = subparsers.add_parser("add-member", help="Add user to a project with a role")
    member_parser.add_argument("--email", help="User email")
    member_parser.add_argument("--project-id", help="Project ID")
    member_parser.add_argument("--role", help="Role (ADMIN, AUDITOR, REVIEWER, VIEWER)", default="ADMIN")
    member_parser.set_defaults(func=_create_admin_project_membership)

    # verify-config
    verify_parser = subparsers.add_parser("verify-config", help="Validate production configuration")
    verify_parser.set_defaults(func=_verify_config)

    # migrate
    migrate_parser = subparsers.add_parser("migrate", help="Run pending database migrations")
    migrate_parser.set_defaults(func=_migrate)

    # migrate-status
    status_parser = subparsers.add_parser("migrate-status", help="Show migration status")
    status_parser.set_defaults(func=_migrate_status)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
