#!/usr/bin/env python3
"""Migrate all workspace databases discovered from the control database.

Connects to the control database, discovers all active workspace databases,
and runs server/migrations/*.sql against each one.

Usage:
    # Using environment variables (AZURE_SQL_SERVER + CONTROL_DB_NAME):
    python scripts/migrate-all-workspaces.py

    # Explicit connection:
    python scripts/migrate-all-workspaces.py --server <server> --control-db <control-db>

    # Dry run (show what would be applied):
    python scripts/migrate-all-workspaces.py --dry-run

    # Show migration status:
    python scripts/migrate-all-workspaces.py --status
"""

import argparse
import os
import struct
import sys
from pathlib import Path

import pyodbc

# Import migration logic from the existing migrate.py
# migrate.py lives at server/scripts/migrate.py; this script lives at scripts/
REPO_ROOT = Path(__file__).parent.parent
MIGRATE_MODULE = REPO_ROOT / "server" / "scripts"
sys.path.insert(0, str(MIGRATE_MODULE))
from migrate import run_migrations  # noqa: E402


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


def discover_workspaces(server: str, control_db: str) -> list[dict]:
    """Query control database for all active workspace databases."""
    conn = get_connection(server, control_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, display_name, db_name FROM workspaces WHERE is_archived = 0 ORDER BY name"
    )
    columns = [col[0] for col in cursor.description]
    workspaces = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return workspaces


def main():
    parser = argparse.ArgumentParser(
        description="Run migrations across all workspace databases discovered from control DB"
    )
    parser.add_argument("--server", help="SQL server hostname")
    parser.add_argument("--control-db", help="Control database name")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be applied")
    parser.add_argument("--status", action="store_true", help="Show migration status only")
    args = parser.parse_args()

    server = args.server or os.environ.get("AZURE_SQL_SERVER", "")
    control_db = args.control_db or os.environ.get("CONTROL_DB_NAME", "")

    if not server:
        print("ERROR: SQL server not specified. Use --server or set AZURE_SQL_SERVER.")
        sys.exit(1)
    if not control_db:
        print("ERROR: Control database not specified. Use --control-db or set CONTROL_DB_NAME.")
        sys.exit(1)

    print(f"=== Workspace Migration ===")
    print(f"Server:     {server}")
    print(f"Control DB: {control_db}")

    # Discover workspaces
    try:
        workspaces = discover_workspaces(server, control_db)
    except Exception as e:
        print(f"\nERROR: Could not connect to control database: {e}")
        sys.exit(1)

    if not workspaces:
        print("\nNo active workspaces found in control database.")
        sys.exit(0)

    print(f"\nDiscovered {len(workspaces)} active workspace(s):")
    for ws in workspaces:
        print(f"  {ws['name']} ({ws['display_name']}) -> db: {ws['db_name']}")

    # Run migrations on each workspace database
    all_ok = True
    results = []
    for ws in workspaces:
        db_name = ws["db_name"]
        print(f"\n{'='*60}")
        print(f"Workspace: {ws['name']} ({ws['display_name']})")
        print(f"Database:  {db_name}")
        print(f"{'='*60}")

        ok = run_migrations(server, db_name, dry_run=args.dry_run, status_only=args.status)
        results.append({"workspace": ws["name"], "database": db_name, "ok": ok})
        if not ok:
            all_ok = False

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for r in results:
        status = "OK" if r["ok"] else "FAILED"
        print(f"  {r['workspace']:<20} {r['database']:<30} {status}")

    if all_ok:
        print(f"\nAll {len(results)} workspace(s) migrated successfully.")
    else:
        failed = [r for r in results if not r["ok"]]
        print(f"\n{len(failed)} of {len(results)} workspace(s) FAILED.")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
