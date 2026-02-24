#!/usr/bin/env python3
"""
Token management CLI for Meeting Intelligence.

Usage:
  python manage_tokens.py create --client "Claude Desktop" --email "user@company.com" --expires 365
  python manage_tokens.py list
  python manage_tokens.py revoke --token-id 3
  python manage_tokens.py rotate --token-id 3 --expires 365
  python manage_tokens.py migrate  # One-time: import from MCP_AUTH_TOKENS env var

Requires:
  - pyodbc (with ODBC Driver 18 for SQL Server)
  - azure-identity
  - Environment variables: AZURE_SQL_SERVER, AZURE_SQL_DATABASE
"""

import argparse
import hashlib
import json
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
    """Create a pyodbc connection with Azure AD token auth.

    Reads AZURE_SQL_SERVER and AZURE_SQL_DATABASE from environment variables.
    Uses DefaultAzureCredential (picks up az login on dev machines, managed identity in Azure).
    """
    import pyodbc
    from azure.identity import DefaultAzureCredential

    server = os.environ.get("AZURE_SQL_SERVER", "")
    database = os.environ.get("AZURE_SQL_DATABASE", "meeting-intelligence")

    if not server:
        print("Error: AZURE_SQL_SERVER environment variable not set.")
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


def cmd_create(args):
    plaintext_token = secrets.token_urlsafe(32)
    token_hash = hash_token(plaintext_token)

    expires_at = None
    if args.expires is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=args.expires)

    with get_db() as cursor:
        cursor.execute(
            """
            INSERT INTO ClientToken (TokenHash, ClientName, ClientEmail, CreatedBy, ExpiresAt, Notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (token_hash, args.client, args.email, "cli-admin", expires_at, args.notes)
        )

    print(f"\n=== Token Created ===")
    print(f"Client:  {args.client}")
    print(f"Email:   {args.email}")
    print(f"Expires: {expires_at.isoformat() if expires_at else 'never'}")
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
    with get_db() as cursor:
        cursor.execute(
            """
            SELECT TokenId, ClientName, ClientEmail, IsActive,
                   ExpiresAt, CreatedAt, CreatedBy, LastUsedAt, Notes
            FROM ClientToken
            ORDER BY CreatedAt DESC
            """
        )
        tokens = _rows_to_list(cursor, cursor.fetchall())

    if not tokens:
        print("No tokens found.")
        return

    print(f"\n{'ID':<5} {'Client':<20} {'Email':<30} {'Active':<8} {'Expires':<25} {'Last Used':<25}")
    print("-" * 120)
    for t in tokens:
        print(
            f"{t['TokenId']:<5} {t['ClientName']:<20} {t['ClientEmail']:<30} "
            f"{'Yes' if t['IsActive'] else 'No':<8} "
            f"{str(t['ExpiresAt'] or 'Never'):<25} "
            f"{str(t['LastUsedAt'] or 'Never'):<25}"
        )


def cmd_revoke(args):
    with get_db() as cursor:
        cursor.execute(
            "UPDATE ClientToken SET IsActive = 0 WHERE TokenId = ?",
            (args.token_id,)
        )
        if cursor.rowcount > 0:
            print(f"Token {args.token_id} revoked. May remain cached for up to 5 minutes.")
        else:
            print(f"Token {args.token_id} not found.")


def cmd_rotate(args):
    # Get old token's client info
    with get_db() as cursor:
        cursor.execute(
            """
            SELECT TokenId, ClientName, ClientEmail, IsActive,
                   ExpiresAt, CreatedAt, CreatedBy, LastUsedAt, Notes
            FROM ClientToken
            ORDER BY CreatedAt DESC
            """
        )
        tokens = _rows_to_list(cursor, cursor.fetchall())

    old_token = next((t for t in tokens if t["TokenId"] == args.token_id), None)
    if not old_token:
        print(f"Error: Token {args.token_id} not found.")
        return

    # Revoke old token
    with get_db() as cursor:
        cursor.execute(
            "UPDATE ClientToken SET IsActive = 0 WHERE TokenId = ?",
            (args.token_id,)
        )
    print(f"Old token {args.token_id} revoked.")

    # Create new token with same client info
    plaintext_token = secrets.token_urlsafe(32)
    token_hash = hash_token(plaintext_token)

    expires_at = None
    if args.expires is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=args.expires)

    with get_db() as cursor:
        cursor.execute(
            """
            INSERT INTO ClientToken (TokenHash, ClientName, ClientEmail, CreatedBy, ExpiresAt, Notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (token_hash, old_token["ClientName"], old_token["ClientEmail"],
             "cli-admin-rotation", expires_at,
             f"Rotated from TokenId {args.token_id}")
        )

    print(f"\n=== New Token Created ===")
    print(f"TOKEN (save this -- it will NOT be shown again):")
    print(f"  {plaintext_token}")


def cmd_migrate(args):
    """One-time migration from MCP_AUTH_TOKENS env var.

    The legacy system stored hashes as tokens — clients sent the hash directly.
    The existing_hash values are already SHA256(plaintext), so we store them
    directly. Do NOT re-hash (that was the old double-hash bug).

    NOTE: Legacy clients using hash-as-token will need new tokens via 'create'.
    """
    if args.json:
        tokens = json.loads(args.json)
    else:
        mcp_auth_tokens = os.environ.get("MCP_AUTH_TOKENS", "")
        if not mcp_auth_tokens:
            print("No tokens found in MCP_AUTH_TOKENS environment variable.")
            return
        tokens = json.loads(mcp_auth_tokens)

    if not tokens:
        print("No tokens found in MCP_AUTH_TOKENS.")
        return

    print(f"Migrating {len(tokens)} tokens from environment variable...")
    for existing_hash, email in tokens.items():
        # existing_hash is already SHA256(plaintext) — store directly, do NOT re-hash.
        # (Previously this did SHA256(existing_hash) = double-hash, which was wrong.)
        client_name = email.split("@")[0]
        print(f"  Migrating: {email} (hash: {existing_hash[:12]}...)")

        try:
            with get_db() as cursor:
                cursor.execute(
                    """
                    INSERT INTO ClientToken (TokenHash, ClientName, ClientEmail, CreatedBy, Notes)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (existing_hash, client_name, email, "cli-migration",
                     "Migrated from MCP_AUTH_TOKENS env var")
                )
        except Exception as e:
            print(f"    Error: {e}")

    print(f"\nMigration complete. {len(tokens)} tokens imported.")
    print("NOTE: Legacy clients using hash-as-token will need new tokens via 'create'.")
    print("You can now remove MCP_AUTH_TOKENS from environment variables.")


def main():
    parser = argparse.ArgumentParser(description="Meeting Intelligence Token Manager")
    sub = parser.add_subparsers(dest="command")

    # create
    p_create = sub.add_parser("create", help="Create a new client token")
    p_create.add_argument("--client", required=True, help="Client name")
    p_create.add_argument("--email", required=True, help="Client email")
    p_create.add_argument("--expires", type=int, help="Expiry in days (default: never)")
    p_create.add_argument("--notes", help="Admin notes")

    # list
    sub.add_parser("list", help="List all tokens")

    # revoke
    p_revoke = sub.add_parser("revoke", help="Revoke a token")
    p_revoke.add_argument("--token-id", type=int, required=True)

    # rotate
    p_rotate = sub.add_parser("rotate", help="Revoke old token and create new one")
    p_rotate.add_argument("--token-id", type=int, required=True)
    p_rotate.add_argument("--expires", type=int, help="Expiry in days for new token")

    # migrate
    p_migrate = sub.add_parser("migrate", help="Migrate from MCP_AUTH_TOKENS env var")
    p_migrate.add_argument("--json", help="JSON string if not in env var")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    commands = {
        "create": cmd_create,
        "list": cmd_list,
        "revoke": cmd_revoke,
        "rotate": cmd_rotate,
        "migrate": cmd_migrate,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
