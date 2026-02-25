#!/usr/bin/env python3
"""
Token management CLI for Meeting Intelligence — Control Database.

Manages tokens, users, and workspace memberships in the control database.

Usage:
  python manage_tokens.py create --user EMAIL --workspace WORKSPACE --role ROLE [--expires DAYS] [--notes TEXT]
  python manage_tokens.py list
  python manage_tokens.py revoke --token-id ID
  python manage_tokens.py add-membership --user EMAIL --workspace WORKSPACE --role ROLE
  python manage_tokens.py remove-membership --user EMAIL --workspace WORKSPACE
  python manage_tokens.py list-users

Requires:
  - pyodbc (with ODBC Driver 18 for SQL Server)
  - azure-identity
  - Environment variables: AZURE_SQL_SERVER, CONTROL_DB_NAME
"""

import argparse
import hashlib
import os
import secrets
import struct
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone


def hash_token(plaintext: str) -> str:
    """Single SHA256 hash of a plaintext token.

    This MUST match the hashing in main.py:validate_mcp_token().
    The app does: hashlib.sha256(token.encode()).hexdigest()
    Any change here will break token validation.
    """
    return hashlib.sha256(plaintext.encode()).hexdigest()


def _get_connection():
    """Create a pyodbc connection to the control database with Azure AD token auth.

    Reads AZURE_SQL_SERVER and CONTROL_DB_NAME from environment variables.
    Uses DefaultAzureCredential (picks up az login on dev, managed identity in Azure).
    """
    import pyodbc
    from azure.identity import DefaultAzureCredential

    server = os.environ.get("AZURE_SQL_SERVER", "")
    database = os.environ.get("CONTROL_DB_NAME", "")

    if not server:
        print("Error: AZURE_SQL_SERVER environment variable not set.")
        raise SystemExit(1)
    if not database:
        print("Error: CONTROL_DB_NAME environment variable not set.")
        raise SystemExit(1)

    credential = DefaultAzureCredential()
    token_bytes = credential.get_token(
        "https://database.windows.net/.default"
    ).token.encode("UTF-16-LE")
    token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)

    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"Encrypt=yes;TrustServerCertificate=no;"
    )

    SQL_COPT_SS_ACCESS_TOKEN = 1256
    return pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})


@contextmanager
def get_db():
    """Context manager for database operations with auto-commit."""
    conn = _get_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def _rows_to_list(cursor, rows):
    """Convert pyodbc rows to a list of dicts."""
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def _get_or_create_user(cursor, email, created_by="cli-admin"):
    """Get existing user ID or create a new user. Returns user_id."""
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    if row:
        return row[0]
    display_name = email.split("@")[0]
    cursor.execute(
        """
        INSERT INTO users (email, display_name, created_by)
        OUTPUT inserted.id
        VALUES (?, ?, ?)
        """,
        (email, display_name, created_by),
    )
    return cursor.fetchone()[0]


def _get_workspace_id(cursor, workspace_name):
    """Look up workspace by name (slug). Returns workspace_id or None."""
    cursor.execute("SELECT id FROM workspaces WHERE name = ?", (workspace_name,))
    row = cursor.fetchone()
    return row[0] if row else None


def _ensure_membership(cursor, user_id, workspace_id, role, added_by="cli-admin"):
    """Create workspace membership if it doesn't exist. Returns True if created."""
    cursor.execute(
        "SELECT id FROM workspace_members WHERE user_id = ? AND workspace_id = ?",
        (user_id, workspace_id),
    )
    if cursor.fetchone():
        return False
    cursor.execute(
        "INSERT INTO workspace_members (user_id, workspace_id, role, added_by) VALUES (?, ?, ?, ?)",
        (user_id, workspace_id, role, added_by),
    )
    return True


# ==========================================================================
# Commands
# ==========================================================================

def cmd_create(args):
    """Create a user, assign to workspace, and generate a token."""
    plaintext_token = secrets.token_urlsafe(32)
    token_hash = hash_token(plaintext_token)

    expires_at = None
    if args.expires is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=args.expires)

    with get_db() as cursor:
        # 1. Get or create user
        user_id = _get_or_create_user(cursor, args.user)

        # 2. Verify workspace exists
        workspace_id = _get_workspace_id(cursor, args.workspace)
        if workspace_id is None:
            print(f"Error: Workspace '{args.workspace}' not found.")
            print("Available workspaces:")
            cursor.execute("SELECT name, display_name FROM workspaces ORDER BY name")
            for row in cursor.fetchall():
                print(f"  {row[0]} ({row[1]})")
            return

        # 3. Create or verify membership
        created = _ensure_membership(cursor, user_id, workspace_id, args.role)
        membership_status = "created" if created else "already exists"

        # 4. Generate token
        client_name = f"{args.user.split('@')[0]}-{args.workspace}"
        cursor.execute(
            """
            INSERT INTO tokens (token_hash, user_id, client_name, created_by, expires_at, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (token_hash, user_id, client_name, "cli-admin", expires_at, args.notes),
        )

    print(f"\n=== Token Created ===")
    print(f"User:       {args.user}")
    print(f"Workspace:  {args.workspace} (role: {args.role}, membership {membership_status})")
    print(f"Expires:    {expires_at.isoformat() if expires_at else 'never'}")
    print()
    print(f"TOKEN (save this -- it will NOT be shown again):")
    print(f"  {plaintext_token}")
    print()
    print(f"For Claude Desktop config.json:")
    print(f'  "url": "https://YOUR-URL/sse?token={plaintext_token}"')
    print()
    print(f"For Copilot Studio:")
    print(f'  URL: https://YOUR-URL/mcp/{plaintext_token}')


def cmd_list(args):
    """List all tokens with user and workspace info."""
    with get_db() as cursor:
        cursor.execute(
            """
            SELECT t.id, t.client_name, u.email, t.is_active,
                   t.expires_at, t.created_at, t.created_by, t.notes
            FROM tokens t
            JOIN users u ON u.id = t.user_id
            ORDER BY t.created_at DESC
            """
        )
        tokens = _rows_to_list(cursor, cursor.fetchall())

    if not tokens:
        print("No tokens found.")
        return

    print(f"\n{'ID':<5} {'Client':<25} {'Email':<30} {'Active':<8} {'Expires':<25}")
    print("-" * 100)
    for t in tokens:
        print(
            f"{t['id']:<5} {(t['client_name'] or ''):<25} {t['email']:<30} "
            f"{'Yes' if t['is_active'] else 'No':<8} "
            f"{str(t['expires_at'] or 'Never'):<25}"
        )


def cmd_revoke(args):
    """Revoke a token by ID."""
    with get_db() as cursor:
        cursor.execute(
            "UPDATE tokens SET is_active = 0, revoked_at = SYSUTCDATETIME() WHERE id = ?",
            (args.token_id,),
        )
        if cursor.rowcount > 0:
            print(f"Token {args.token_id} revoked. May remain cached for up to 5 minutes.")
        else:
            print(f"Token {args.token_id} not found.")


def cmd_add_membership(args):
    """Add a user to a workspace."""
    with get_db() as cursor:
        user_id = _get_or_create_user(cursor, args.user)
        workspace_id = _get_workspace_id(cursor, args.workspace)
        if workspace_id is None:
            print(f"Error: Workspace '{args.workspace}' not found.")
            return

        created = _ensure_membership(cursor, user_id, workspace_id, args.role)
        if created:
            print(f"Added {args.user} as {args.role} to workspace '{args.workspace}'.")
        else:
            # Update role if membership already exists
            cursor.execute(
                "UPDATE workspace_members SET role = ? WHERE user_id = ? AND workspace_id = ?",
                (args.role, user_id, workspace_id),
            )
            print(f"Updated {args.user} role to {args.role} in workspace '{args.workspace}'.")


def cmd_remove_membership(args):
    """Remove a user from a workspace."""
    with get_db() as cursor:
        cursor.execute("SELECT id FROM users WHERE email = ?", (args.user,))
        user_row = cursor.fetchone()
        if not user_row:
            print(f"Error: User '{args.user}' not found.")
            return
        user_id = user_row[0]

        workspace_id = _get_workspace_id(cursor, args.workspace)
        if workspace_id is None:
            print(f"Error: Workspace '{args.workspace}' not found.")
            return

        cursor.execute(
            "DELETE FROM workspace_members WHERE user_id = ? AND workspace_id = ?",
            (user_id, workspace_id),
        )
        if cursor.rowcount > 0:
            print(f"Removed {args.user} from workspace '{args.workspace}'.")
        else:
            print(f"{args.user} is not a member of workspace '{args.workspace}'.")


def cmd_list_users(args):
    """List all users with their workspace memberships."""
    with get_db() as cursor:
        cursor.execute(
            """
            SELECT u.id, u.email, u.display_name, u.is_org_admin,
                   (SELECT COUNT(*) FROM tokens t WHERE t.user_id = u.id AND t.is_active = 1) AS active_tokens
            FROM users u
            ORDER BY u.email
            """
        )
        users = _rows_to_list(cursor, cursor.fetchall())

        if not users:
            print("No users found.")
            return

        print(f"\n{'ID':<5} {'Email':<30} {'Display Name':<20} {'Admin':<7} {'Tokens':<8}")
        print("-" * 80)
        for u in users:
            print(
                f"{u['id']:<5} {u['email']:<30} {(u['display_name'] or ''):<20} "
                f"{'Yes' if u['is_org_admin'] else 'No':<7} "
                f"{u['active_tokens']:<8}"
            )

        # Show memberships
        print(f"\n--- Workspace Memberships ---")
        cursor.execute(
            """
            SELECT u.email, w.name, w.display_name, wm.role
            FROM workspace_members wm
            JOIN users u ON u.id = wm.user_id
            JOIN workspaces w ON w.id = wm.workspace_id
            ORDER BY u.email, w.name
            """
        )
        rows = cursor.fetchall()
        if rows:
            current_email = None
            for row in rows:
                if row[0] != current_email:
                    current_email = row[0]
                    print(f"\n  {current_email}:")
                print(f"    {row[1]} ({row[2]}) — {row[3]}")
        else:
            print("  No memberships found.")


# ==========================================================================
# CLI Entry Point
# ==========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Meeting Intelligence Token Manager (Control Database)",
    )
    sub = parser.add_subparsers(dest="command")

    # create
    p_create = sub.add_parser("create", help="Create token + user + workspace membership")
    p_create.add_argument("--user", required=True, help="User email address")
    p_create.add_argument("--workspace", required=True, help="Workspace name (slug)")
    p_create.add_argument("--role", required=True, choices=["viewer", "member", "chair"],
                          help="Role in workspace")
    p_create.add_argument("--expires", type=int, help="Expiry in days (default: never)")
    p_create.add_argument("--notes", help="Admin notes")

    # list
    sub.add_parser("list", help="List all tokens")

    # revoke
    p_revoke = sub.add_parser("revoke", help="Revoke a token")
    p_revoke.add_argument("--token-id", type=int, required=True)

    # add-membership
    p_add = sub.add_parser("add-membership", help="Add user to workspace")
    p_add.add_argument("--user", required=True, help="User email address")
    p_add.add_argument("--workspace", required=True, help="Workspace name (slug)")
    p_add.add_argument("--role", required=True, choices=["viewer", "member", "chair"],
                       help="Role in workspace")

    # remove-membership
    p_rm = sub.add_parser("remove-membership", help="Remove user from workspace")
    p_rm.add_argument("--user", required=True, help="User email address")
    p_rm.add_argument("--workspace", required=True, help="Workspace name (slug)")

    # list-users
    sub.add_parser("list-users", help="List all users with memberships")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    commands = {
        "create": cmd_create,
        "list": cmd_list,
        "revoke": cmd_revoke,
        "add-membership": cmd_add_membership,
        "remove-membership": cmd_remove_membership,
        "list-users": cmd_list_users,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
