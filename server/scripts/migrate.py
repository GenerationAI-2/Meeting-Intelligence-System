#!/usr/bin/env python3
"""Database migration runner for Meeting Intelligence.

Applies SQL migration files from server/migrations/ in order.
Tracks applied migrations in a _MigrationHistory table per database.
Designed to work across N client databases.

Usage:
    # Apply to current environment (reads .env):
    uv run python -m scripts.migrate

    # Apply to a specific database:
    uv run python -m scripts.migrate --server <server> --database <db>

    # Dry run (show what would be applied):
    uv run python -m scripts.migrate --dry-run

    # Show migration status:
    uv run python -m scripts.migrate --status

    # Apply across all environments:
    uv run python -m scripts.migrate --all
"""

import argparse
import hashlib
import os
import sys
import struct
from datetime import datetime, timezone
from pathlib import Path

import pyodbc

# Environment configs for --all mode
ENVIRONMENTS = {
    "team": {
        "server": "genai-sql-server.database.windows.net",
        "database": "meeting-intelligence-team",
    },
    "demo": {
        "server": "genai-sql-server.database.windows.net",
        "database": "meeting-intelligence",
    },
    "marshall": {
        "server": "genai-sql-server.database.windows.net",
        "database": "mi-marshall",
    },
    "testing-instance": {
        "server": "mi-testing-instance-sql.database.windows.net",
        "database": "mi-testing-instance",
    },
}

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"

TRACKING_TABLE_SQL = """
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = '_MigrationHistory')
BEGIN
    CREATE TABLE _MigrationHistory (
        MigrationId     NVARCHAR(255)   NOT NULL PRIMARY KEY,
        AppliedAt       DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
        AppliedBy       NVARCHAR(128)   NOT NULL,
        Checksum        NVARCHAR(64)    NOT NULL
    );
END
"""


def get_connection(server: str, database: str) -> pyodbc.Connection:
    """Create a connection using Azure AD token auth."""
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    token_bytes = credential.get_token(
        "https://database.windows.net/.default"
    ).token.encode("UTF-16-LE")
    token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)

    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"Encrypt=yes;TrustServerCertificate=no;"
    )
    SQL_COPT_SS_ACCESS_TOKEN = 1256
    return pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})


def get_migration_files() -> list[tuple[str, Path]]:
    """Get all .sql migration files sorted by name."""
    if not MIGRATIONS_DIR.exists():
        return []
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return [(f.stem, f) for f in files]


def file_checksum(path: Path) -> str:
    """SHA256 checksum of a migration file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def get_applied_migrations(conn: pyodbc.Connection) -> dict[str, dict]:
    """Get already-applied migrations from tracking table."""
    cursor = conn.cursor()
    cursor.execute(TRACKING_TABLE_SQL)
    conn.commit()

    cursor.execute("SELECT MigrationId, AppliedAt, Checksum FROM _MigrationHistory ORDER BY MigrationId")
    rows = cursor.fetchall()
    return {row[0]: {"applied_at": row[1], "checksum": row[2]} for row in rows}


def apply_migration(conn: pyodbc.Connection, migration_id: str, path: Path, applied_by: str) -> None:
    """Apply a single migration file within a transaction.

    If any statement fails, the entire migration is rolled back and
    _MigrationHistory is not updated.
    """
    sql = path.read_text(encoding="utf-8")
    checksum = file_checksum(path)

    conn.autocommit = False
    cursor = conn.cursor()
    try:
        # Execute migration SQL (may contain multiple statements separated by GO)
        # Split on GO statements (must be alone on a line)
        batches = _split_on_go(sql)
        for batch in batches:
            batch = batch.strip()
            if batch:
                cursor.execute(batch)

        # Record in tracking table (only if all statements succeeded)
        cursor.execute(
            "INSERT INTO _MigrationHistory (MigrationId, AppliedBy, Checksum) VALUES (?, ?, ?)",
            (migration_id, applied_by, checksum),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _split_on_go(sql: str) -> list[str]:
    """Split SQL on GO batch separators (must be alone on a line)."""
    import re
    return re.split(r"^\s*GO\s*$", sql, flags=re.MULTILINE | re.IGNORECASE)


def run_migrations(server: str, database: str, dry_run: bool = False, status_only: bool = False) -> bool:
    """Run pending migrations on a single database. Returns True if all succeeded."""
    label = f"{server}/{database}"
    print(f"\n--- {label} ---")

    try:
        conn = get_connection(server, database)
    except Exception as e:
        print(f"  ERROR: Could not connect: {e}")
        return False

    applied = get_applied_migrations(conn)
    migrations = get_migration_files()

    if status_only:
        print(f"  Applied: {len(applied)}, Available: {len(migrations)}")
        for mid, path in migrations:
            status = "APPLIED" if mid in applied else "PENDING"
            checksum = file_checksum(path)
            info = ""
            if mid in applied:
                stored = applied[mid]["checksum"]
                if stored != checksum:
                    info = " (CHECKSUM MISMATCH!)"
            print(f"    [{status}] {mid}{info}")
        conn.close()
        return True

    pending = [(mid, path) for mid, path in migrations if mid not in applied]
    if not pending:
        print("  All migrations already applied.")
        conn.close()
        return True

    print(f"  {len(pending)} pending migration(s):")
    for mid, path in pending:
        print(f"    - {mid}")

    if dry_run:
        print("  (dry run — no changes applied)")
        conn.close()
        return True

    applied_by = os.environ.get("USER", "migrate-script")
    success = True
    for mid, path in pending:
        try:
            print(f"  Applying {mid}...", end=" ", flush=True)
            apply_migration(conn, mid, path, applied_by)
            print("OK")
        except Exception as e:
            print(f"FAILED: {e}")
            success = False
            break

    conn.close()
    return success


def main():
    parser = argparse.ArgumentParser(description="Meeting Intelligence database migration runner")
    parser.add_argument("--server", help="SQL server hostname")
    parser.add_argument("--database", help="Database name")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be applied without executing")
    parser.add_argument("--status", action="store_true", help="Show migration status only")
    parser.add_argument("--all", action="store_true", help="Run against all known environments")
    args = parser.parse_args()

    if args.all:
        print("=== Running migrations across all environments ===")
        all_ok = True
        for env_name, config in ENVIRONMENTS.items():
            print(f"\n=== Environment: {env_name} ===")
            ok = run_migrations(config["server"], config["database"], args.dry_run, args.status)
            if not ok:
                all_ok = False
        sys.exit(0 if all_ok else 1)

    if args.server and args.database:
        ok = run_migrations(args.server, args.database, args.dry_run, args.status)
        sys.exit(0 if ok else 1)

    # Default: use environment settings
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from config import get_settings
        settings = get_settings()
        if not settings.azure_sql_server:
            print("ERROR: AZURE_SQL_SERVER not configured. Use --server/--database or set .env")
            sys.exit(1)
        ok = run_migrations(settings.azure_sql_server, settings.azure_sql_database, args.dry_run, args.status)
        sys.exit(0 if ok else 1)
    except Exception as e:
        print(f"ERROR: {e}")
        print("Use --server and --database to specify connection details directly.")
        sys.exit(1)


if __name__ == "__main__":
    main()
