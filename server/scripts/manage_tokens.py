#!/usr/bin/env python3
"""
Token management CLI for Meeting Intelligence.

Usage:
  python manage_tokens.py create --client "Claude Desktop" --email "user@company.com" --expires 365
  python manage_tokens.py list
  python manage_tokens.py revoke --token-id 3
  python manage_tokens.py rotate --token-id 3 --expires 365
  python manage_tokens.py migrate  # One-time: import from MCP_AUTH_TOKENS env var
"""

import argparse
import hashlib
import json
import os
import sys

# Add server/src to path so we can import the database module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from database import (
    create_client_token,
    insert_token_hash,
    revoke_client_token,
    list_client_tokens,
)
from config import get_settings


def cmd_create(args):
    result = create_client_token(
        client_name=args.client,
        client_email=args.email,
        created_by="cli-admin",
        expires_days=args.expires,
        notes=args.notes,
    )

    if isinstance(result, dict) and result.get("error"):
        print(f"Error: {result['message']}")
        return

    print(f"\n=== Token Created ===")
    print(f"Client:  {result['client_name']}")
    print(f"Email:   {result['client_email']}")
    print(f"Expires: {result['expires_at']}")
    print()
    print(f"TOKEN (save this -- it will NOT be shown again):")
    print(f"  {result['token']}")
    print()
    print(f"For Claude Desktop config.json:")
    print(f'  "url": "https://YOUR-URL/sse?token={result["token"]}"')
    print()
    print(f"For Copilot Studio:")
    print(f'  URL: https://YOUR-URL/mcp/{result["token"]}')


def cmd_list(args):
    tokens = list_client_tokens()

    if isinstance(tokens, dict) and tokens.get("error"):
        print(f"Error: {tokens['message']}")
        return

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
    success = revoke_client_token(args.token_id)
    if isinstance(success, dict) and success.get("error"):
        print(f"Error: {success['message']}")
    elif success:
        print(f"Token {args.token_id} revoked. May remain cached for up to 5 minutes.")
    else:
        print(f"Token {args.token_id} not found.")


def cmd_rotate(args):
    # Get old token's client info before revoking
    tokens = list_client_tokens()
    if isinstance(tokens, dict) and tokens.get("error"):
        print(f"Error: {tokens['message']}")
        return

    old_token = next((t for t in tokens if t["TokenId"] == args.token_id), None)
    if not old_token:
        print(f"Error: Token {args.token_id} not found.")
        return

    # Revoke old token
    revoke_client_token(args.token_id)
    print(f"Old token {args.token_id} revoked.")

    # Create new token with same client info
    result = create_client_token(
        client_name=old_token["ClientName"],
        client_email=old_token["ClientEmail"],
        created_by="cli-admin-rotation",
        expires_days=args.expires,
        notes=f"Rotated from TokenId {args.token_id}",
    )

    if isinstance(result, dict) and result.get("error"):
        print(f"Error creating new token: {result['message']}")
        return

    print(f"\n=== New Token Created ===")
    print(f"TOKEN (save this -- it will NOT be shown again):")
    print(f"  {result['token']}")


def cmd_migrate(args):
    """One-time migration from MCP_AUTH_TOKENS env var.

    The current system stores hashes as tokens — clients send the hash directly.
    The new system hashes incoming tokens before DB lookup.
    So we store SHA256(existing_hash) so existing clients continue working
    without updating their token values.
    """
    if args.json:
        tokens = json.loads(args.json)
    else:
        settings = get_settings()
        tokens = settings.get_mcp_auth_tokens_dict()

    if not tokens:
        print("No tokens found in MCP_AUTH_TOKENS.")
        return

    print(f"Migrating {len(tokens)} tokens from environment variable...")
    for existing_hash, email in tokens.items():
        # The hash IS the token in the current system. Clients send this hash.
        # The new middleware does SHA256(incoming_token) before DB lookup.
        # So we store SHA256(existing_hash) to match the double-hash.
        new_hash = hashlib.sha256(existing_hash.encode()).hexdigest()
        client_name = email.split("@")[0]
        print(f"  Migrating: {email} (original hash: {existing_hash[:12]}...)")

        result = insert_token_hash(
            token_hash=new_hash,
            client_name=client_name,
            client_email=email,
            created_by="cli-migration",
            notes="Migrated from MCP_AUTH_TOKENS env var",
        )

        if isinstance(result, dict) and result.get("error"):
            print(f"    Error: {result['message']}")

    print(f"\nMigration complete. {len(tokens)} tokens imported.")
    print("Existing clients will continue working with their current tokens.")
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
