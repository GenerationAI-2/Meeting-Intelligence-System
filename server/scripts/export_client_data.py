#!/usr/bin/env python3
"""Export all client data from a Meeting Intelligence database.

Exports meetings, actions, and decisions to JSON files for client offboarding.
Uses the same Azure AD token auth as the main application.

Usage:
    uv run python -m scripts.export_client_data --server <server> --database <db> --output <dir>

Example:
    uv run python -m scripts.export_client_data \
        --server genai-sql-server.database.windows.net \
        --database mi-marshall \
        --output ./exports/marshall-2026-02-12
"""

import argparse
import json
import os
import struct
import sys
from datetime import datetime, date, timezone
from pathlib import Path

import pyodbc


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


def json_serializer(obj):
    """Handle datetime and date serialization."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def export_table(cursor, table_name: str, output_dir: Path) -> int:
    """Export a table to JSON. Returns row count."""
    cursor.execute(f"SELECT * FROM [{table_name}] ORDER BY 1")
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    output_file = output_dir / f"{table_name.lower()}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, default=json_serializer, ensure_ascii=False)

    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Export client data for offboarding")
    parser.add_argument("--server", required=True, help="SQL server hostname")
    parser.add_argument("--database", required=True, help="Database name")
    parser.add_argument("--output", required=True, help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Exporting data from {args.database} ===")
    print(f"Output: {output_dir}")
    print()

    try:
        conn = get_connection(args.server, args.database)
    except Exception as e:
        print(f"ERROR: Could not connect: {e}")
        sys.exit(1)

    cursor = conn.cursor()
    tables = ["Meeting", "Action", "Decision"]
    total_rows = 0

    for table in tables:
        try:
            count = export_table(cursor, table, output_dir)
            print(f"  {table}: {count} rows exported")
            total_rows += count
        except Exception as e:
            print(f"  {table}: FAILED — {e}")

    conn.close()

    # Write export manifest
    manifest = {
        "database": args.database,
        "server": args.server,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "tables": tables,
        "total_rows": total_rows,
    }
    manifest_file = output_dir / "export-manifest.json"
    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=2)

    print()
    print(f"=== Export complete: {total_rows} total rows ===")
    print(f"Manifest: {manifest_file}")


if __name__ == "__main__":
    main()
