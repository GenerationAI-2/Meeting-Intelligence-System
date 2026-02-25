#!/usr/bin/env python3
"""Upgrade an existing single-database deployment to workspace architecture.

Creates a control database, migrates tokens and users, and registers the
existing database as the "General" workspace.

Usage:
    python scripts/migrate-to-workspaces.py \\
        --server genai-sql-server.database.windows.net \\
        --database meeting-intelligence-team \\
        --control-db meeting-intelligence-team-control

    # With custom app name (for MI user in control DB):
    python scripts/migrate-to-workspaces.py \\
        --server genai-sql-server.database.windows.net \\
        --database meeting-intelligence-team \\
        --control-db meeting-intelligence-team-control \\
        --app-name meeting-intelligence-team

    # Dry run (preview what would happen):
    python scripts/migrate-to-workspaces.py \\
        --server genai-sql-server.database.windows.net \\
        --database meeting-intelligence-team \\
        --control-db meeting-intelligence-team-control \\
        --dry-run

Prerequisites:
    - Azure CLI authenticated (az login) with Entra admin on the SQL Server
    - pyodbc with ODBC Driver 18 for SQL Server
    - azure-identity
"""

import argparse
import re
import struct
import sys
from pathlib import Path

import pyodbc

REPO_ROOT = Path(__file__).parent.parent
CONTROL_SCHEMA_PATH = REPO_ROOT / "scripts" / "control_schema.sql"
GRANT_MI_ACCESS_PATH = REPO_ROOT / "scripts" / "grant-mi-access.sql"


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


def split_on_go(sql: str) -> list[str]:
    """Split SQL on GO batch separators (must be alone on a line)."""
    return re.split(r"^\s*GO\s*$", sql, flags=re.MULTILINE | re.IGNORECASE)


def step_1_create_control_db(server: str, control_db: str, dry_run: bool) -> bool:
    """Create the control database on the server (via master)."""
    print("\n--- Step 1: Create control database ---")

    conn = get_connection(server, "master")
    conn.autocommit = True
    cursor = conn.cursor()

    # Check if database already exists
    cursor.execute(
        "SELECT 1 FROM sys.databases WHERE name = ?", (control_db,)
    )
    if cursor.fetchone():
        print(f"  Database '{control_db}' already exists -- skipping creation")
        conn.close()
        return True

    if dry_run:
        print(f"  [DRY RUN] Would create database: {control_db}")
        conn.close()
        return True

    print(f"  Creating database: {control_db}")
    try:
        cursor.execute(f"CREATE DATABASE [{control_db}]")
        print(f"  Database '{control_db}' created")
    except Exception as e:
        print(f"  ERROR: Failed to create database: {e}")
        conn.close()
        return False

    conn.close()
    return True


def step_2_run_control_schema(server: str, control_db: str, dry_run: bool) -> bool:
    """Apply control_schema.sql to the control database."""
    print("\n--- Step 2: Apply control schema ---")

    if not CONTROL_SCHEMA_PATH.exists():
        print(f"  ERROR: Schema file not found: {CONTROL_SCHEMA_PATH}")
        return False

    schema_sql = CONTROL_SCHEMA_PATH.read_text(encoding="utf-8")

    if dry_run:
        batches = [b.strip() for b in split_on_go(schema_sql) if b.strip()]
        print(f"  [DRY RUN] Would execute {len(batches)} SQL batch(es) against {control_db}")
        return True

    conn = get_connection(server, control_db)
    cursor = conn.cursor()

    # Check if schema already applied (workspaces table exists)
    cursor.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'workspaces'"
    )
    if cursor.fetchone()[0] > 0:
        print("  Control schema already applied -- skipping")
        conn.close()
        return True

    print("  Applying control schema...")
    try:
        for batch in split_on_go(schema_sql):
            batch = batch.strip()
            if batch:
                cursor.execute(batch)
        conn.commit()
        print("  Control schema applied")
    except Exception as e:
        conn.rollback()
        print(f"  ERROR: Failed to apply control schema: {e}")
        conn.close()
        return False

    conn.close()
    return True


def step_3_grant_mi_access(server: str, control_db: str, app_name: str, dry_run: bool) -> bool:
    """Grant managed identity access to the control database."""
    print("\n--- Step 3: Grant MI access to control database ---")

    if not GRANT_MI_ACCESS_PATH.exists():
        print(f"  ERROR: Grant script not found: {GRANT_MI_ACCESS_PATH}")
        return False

    grant_sql = GRANT_MI_ACCESS_PATH.read_text(encoding="utf-8")
    grant_sql = grant_sql.replace("{APP_NAME}", app_name)

    if dry_run:
        print(f"  [DRY RUN] Would grant {app_name} access to {control_db}")
        return True

    conn = get_connection(server, control_db)
    cursor = conn.cursor()

    try:
        for batch in split_on_go(grant_sql):
            batch = batch.strip()
            if batch:
                cursor.execute(batch)
        conn.commit()
        print(f"  MI access granted for [{app_name}] on {control_db}")
    except Exception as e:
        conn.rollback()
        print(f"  ERROR: Failed to grant MI access: {e}")
        conn.close()
        return False

    conn.close()
    return True


def step_4_register_general_workspace(
    server: str, control_db: str, existing_db: str, dry_run: bool
) -> int | None:
    """Register the existing database as the 'General' workspace."""
    print("\n--- Step 4: Register General workspace ---")

    if dry_run:
        print(f"  [DRY RUN] Would register '{existing_db}' as General workspace")
        return 0

    conn = get_connection(server, control_db)
    cursor = conn.cursor()

    # Check if already registered
    cursor.execute("SELECT id FROM workspaces WHERE name = 'general'")
    row = cursor.fetchone()
    if row:
        print(f"  General workspace already registered (id={row[0]}) -- skipping")
        workspace_id = row[0]
        conn.close()
        return workspace_id

    try:
        cursor.execute(
            """
            INSERT INTO workspaces (name, display_name, db_name, is_default, created_by)
            OUTPUT inserted.id
            VALUES ('general', 'General', ?, 1, 'system@generationai.co.nz')
            """,
            (existing_db,),
        )
        workspace_id = cursor.fetchone()[0]
        conn.commit()
        print(f"  General workspace registered (id={workspace_id}, db={existing_db})")
    except Exception as e:
        conn.rollback()
        print(f"  ERROR: Failed to register workspace: {e}")
        conn.close()
        return None

    conn.close()
    return workspace_id


def step_5_migrate_tokens(
    server: str,
    control_db: str,
    existing_db: str,
    workspace_id: int,
    dry_run: bool,
) -> dict:
    """Migrate tokens from workspace DB ClientToken table to control DB."""
    print("\n--- Step 5: Migrate tokens ---")

    stats = {"tokens": 0, "users_created": 0, "users_existing": 0, "memberships": 0}

    # Read tokens from existing workspace database
    try:
        ws_conn = get_connection(server, existing_db)
        ws_cursor = ws_conn.cursor()
    except Exception as e:
        print(f"  ERROR: Could not connect to workspace database: {e}")
        return stats

    # Check if ClientToken table exists
    ws_cursor.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'ClientToken'"
    )
    if ws_cursor.fetchone()[0] == 0:
        print("  No ClientToken table found -- nothing to migrate")
        ws_conn.close()
        return stats

    ws_cursor.execute(
        """
        SELECT TokenHash, ClientName, ClientEmail, IsActive, ExpiresAt,
               CreatedAt, CreatedBy, Notes
        FROM ClientToken
        """
    )
    tokens = []
    for row in ws_cursor.fetchall():
        tokens.append({
            "token_hash": row[0],
            "client_name": row[1],
            "client_email": row[2],
            "is_active": row[3],
            "expires_at": row[4],
            "created_at": row[5],
            "created_by": row[6],
            "notes": row[7],
        })
    ws_conn.close()

    if not tokens:
        print("  No tokens found in ClientToken table")
        return stats

    print(f"  Found {len(tokens)} token(s) to migrate")

    if dry_run:
        for t in tokens:
            print(f"    [DRY RUN] {t['client_email']} ({t['client_name']}) -> General, role=chair")
        stats["tokens"] = len(tokens)
        return stats

    # Migrate to control database
    ctrl_conn = get_connection(server, control_db)
    ctrl_cursor = ctrl_conn.cursor()

    try:
        for t in tokens:
            email = t["client_email"]
            if not email:
                print(f"    SKIP: Token '{t['client_name']}' has no email -- cannot migrate")
                continue

            # Get or create user
            ctrl_cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
            user_row = ctrl_cursor.fetchone()
            if user_row:
                user_id = user_row[0]
                stats["users_existing"] += 1
            else:
                display_name = email.split("@")[0]
                ctrl_cursor.execute(
                    """
                    INSERT INTO users (email, display_name, created_by)
                    OUTPUT inserted.id
                    VALUES (?, ?, 'migrate-to-workspaces')
                    """,
                    (email, display_name),
                )
                user_id = ctrl_cursor.fetchone()[0]
                stats["users_created"] += 1

            # Check if token already migrated
            ctrl_cursor.execute(
                "SELECT id FROM tokens WHERE token_hash = ?", (t["token_hash"],)
            )
            if ctrl_cursor.fetchone():
                print(f"    Token for {email} already exists in control DB -- skipping")
            else:
                ctrl_cursor.execute(
                    """
                    INSERT INTO tokens (token_hash, user_id, client_name, is_active,
                                        created_by, expires_at, notes)
                    VALUES (?, ?, ?, ?, 'migrate-to-workspaces', ?, ?)
                    """,
                    (
                        t["token_hash"],
                        user_id,
                        t["client_name"],
                        t["is_active"],
                        t["expires_at"],
                        t["notes"],
                    ),
                )
                stats["tokens"] += 1

            # Ensure workspace membership (all existing users get chair)
            ctrl_cursor.execute(
                "SELECT id FROM workspace_members WHERE user_id = ? AND workspace_id = ?",
                (user_id, workspace_id),
            )
            if not ctrl_cursor.fetchone():
                ctrl_cursor.execute(
                    """
                    INSERT INTO workspace_members (user_id, workspace_id, role, added_by)
                    VALUES (?, ?, 'chair', 'migrate-to-workspaces')
                    """,
                    (user_id, workspace_id),
                )
                stats["memberships"] += 1

        ctrl_conn.commit()
    except Exception as e:
        ctrl_conn.rollback()
        print(f"  ERROR: Token migration failed: {e}")
        ctrl_conn.close()
        return stats

    ctrl_conn.close()
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Upgrade existing deployment to workspace architecture"
    )
    parser.add_argument(
        "--server", required=True, help="SQL server hostname (e.g., genai-sql-server.database.windows.net)"
    )
    parser.add_argument(
        "--database", required=True, help="Existing workspace database name (e.g., meeting-intelligence-team)"
    )
    parser.add_argument(
        "--control-db", required=True, help="Control database name to create (e.g., meeting-intelligence-team-control)"
    )
    parser.add_argument(
        "--app-name",
        help="Container app managed identity name (default: derived from database name)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview what would happen without making changes"
    )
    args = parser.parse_args()

    app_name = args.app_name or args.database

    print("=" * 60)
    print("Migrate to Workspaces")
    print("=" * 60)
    print(f"Server:       {args.server}")
    print(f"Existing DB:  {args.database}")
    print(f"Control DB:   {args.control_db}")
    print(f"App name:     {app_name}")
    if args.dry_run:
        print("Mode:         DRY RUN")
    print()

    # Step 1: Create control database
    if not step_1_create_control_db(args.server, args.control_db, args.dry_run):
        print("\nFATAL: Could not create control database. Aborting.")
        sys.exit(1)

    # Step 2: Apply control schema
    if not step_2_run_control_schema(args.server, args.control_db, args.dry_run):
        print("\nFATAL: Could not apply control schema. Aborting.")
        sys.exit(1)

    # Step 3: Grant MI access to control database
    if not step_3_grant_mi_access(args.server, args.control_db, app_name, args.dry_run):
        print("\nWARNING: MI access grant failed. You may need to grant access manually.")
        print(f"  See: scripts/grant-mi-access.sql (replace {{APP_NAME}} with {app_name})")

    # Step 4: Register General workspace
    workspace_id = step_4_register_general_workspace(
        args.server, args.control_db, args.database, args.dry_run
    )
    if workspace_id is None:
        print("\nFATAL: Could not register General workspace. Aborting.")
        sys.exit(1)

    # Step 5: Migrate tokens
    stats = step_5_migrate_tokens(
        args.server, args.control_db, args.database, workspace_id, args.dry_run
    )

    # Summary
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"Control database:    {args.control_db}")
    print(f"General workspace:   {args.database} (id={workspace_id})")
    print(f"Tokens migrated:     {stats['tokens']}")
    print(f"Users created:       {stats['users_created']}")
    print(f"Users existing:      {stats['users_existing']}")
    print(f"Memberships created: {stats['memberships']}")

    if args.dry_run:
        print("\n[DRY RUN] No changes were made. Run without --dry-run to apply.")
    else:
        print("\nMigration complete.")
        print("\nNext steps:")
        print(f"  1. Set CONTROL_DB_NAME={args.control_db} on the container app")
        print("  2. Restart the container app to pick up the new config")
        print("  3. Verify MCP tokens still work")
        print("  4. The ClientToken table in the workspace DB was NOT modified")
        print("     (kept for rollback safety)")


if __name__ == "__main__":
    main()
