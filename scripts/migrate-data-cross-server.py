#!/usr/bin/env python3
"""Migrate Meeting/Action/Decision data between Azure SQL databases across servers.

Reads from a source database and writes to a target database. Handles IDENTITY
columns by using SET IDENTITY_INSERT ON. Preserves all original IDs so foreign
key relationships remain intact.

Usage:
    # Dry run (preview row counts):
    python scripts/migrate-data-cross-server.py \
        --source-server genai-sql-server.database.windows.net \
        --source-db meeting-intelligence-team \
        --target-server mi-genai-sql.database.windows.net \
        --target-db mi-genai-team \
        --dry-run

    # Execute migration:
    python scripts/migrate-data-cross-server.py \
        --source-server genai-sql-server.database.windows.net \
        --source-db meeting-intelligence-team \
        --target-server mi-genai-sql.database.windows.net \
        --target-db mi-genai-team

Prerequisites:
    - Azure CLI authenticated (az login)
    - pyodbc with ODBC Driver 18 for SQL Server
    - azure-identity
"""

import argparse
import struct
import sys

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


# Table definitions: (table_name, id_column, columns_in_insert_order)
# Order matters — Meeting first (parent), then Decision and Action (children with FK)
TABLES = [
    (
        "Meeting",
        "MeetingId",
        [
            "MeetingId", "Title", "MeetingDate", "RawTranscript", "Summary",
            "Attendees", "Source", "SourceMeetingId", "Tags",
            "CreatedAt", "CreatedBy", "UpdatedAt", "UpdatedBy",
        ],
    ),
    (
        "Decision",
        "DecisionId",
        [
            "DecisionId", "MeetingId", "DecisionText", "Context",
            "CreatedAt", "CreatedBy",
        ],
    ),
    (
        "Action",
        "ActionId",
        [
            "ActionId", "MeetingId", "ActionText", "Owner", "DueDate",
            "Status", "Notes", "CreatedAt", "CreatedBy", "UpdatedAt", "UpdatedBy",
        ],
    ),
]


def migrate_table(
    src_cursor: pyodbc.Cursor,
    tgt_conn: pyodbc.Connection,
    table_name: str,
    id_column: str,
    columns: list[str],
    dry_run: bool,
) -> int:
    """Migrate all rows from source to target for one table."""
    print(f"\n  --- {table_name} ---")

    # Count source rows
    src_cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
    src_count = src_cursor.fetchone()[0]
    print(f"  Source rows: {src_count}")

    if src_count == 0:
        print("  Nothing to migrate")
        return 0

    # Check target for existing rows
    tgt_cursor = tgt_conn.cursor()
    tgt_cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
    tgt_count = tgt_cursor.fetchone()[0]
    if tgt_count > 0:
        print(f"  WARNING: Target already has {tgt_count} rows — skipping to avoid duplicates")
        return 0

    if dry_run:
        print(f"  [DRY RUN] Would migrate {src_count} rows")
        return src_count

    # Read all source rows
    col_list = ", ".join(f"[{c}]" for c in columns)
    src_cursor.execute(f"SELECT {col_list} FROM [{table_name}] ORDER BY [{id_column}]")
    rows = src_cursor.fetchall()

    # Write to target with IDENTITY_INSERT
    placeholders = ", ".join("?" for _ in columns)
    insert_sql = f"INSERT INTO [{table_name}] ({col_list}) VALUES ({placeholders})"

    tgt_cursor.execute(f"SET IDENTITY_INSERT [{table_name}] ON")

    batch_size = 100
    migrated = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        for row in batch:
            tgt_cursor.execute(insert_sql, tuple(row))
        tgt_conn.commit()
        migrated += len(batch)
        if migrated % 500 == 0 or migrated == len(rows):
            print(f"  Migrated {migrated}/{len(rows)} rows")

    tgt_cursor.execute(f"SET IDENTITY_INSERT [{table_name}] OFF")
    tgt_conn.commit()

    print(f"  Migrated {migrated} rows")
    return migrated


def verify_counts(
    src_cursor: pyodbc.Cursor,
    tgt_cursor: pyodbc.Cursor,
) -> bool:
    """Verify row counts match between source and target."""
    print("\n  --- Verification ---")
    all_match = True
    for table_name, id_column, _ in TABLES:
        src_cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
        src_count = src_cursor.fetchone()[0]
        tgt_cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
        tgt_count = tgt_cursor.fetchone()[0]
        status = "OK" if src_count == tgt_count else "MISMATCH"
        if status == "MISMATCH":
            all_match = False
        print(f"  {table_name}: source={src_count}, target={tgt_count} — {status}")
    return all_match


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Meeting/Action/Decision data between SQL databases"
    )
    parser.add_argument("--source-server", required=True, help="Source SQL server hostname")
    parser.add_argument("--source-db", required=True, help="Source database name")
    parser.add_argument("--target-server", required=True, help="Target SQL server hostname")
    parser.add_argument("--target-db", required=True, help="Target database name")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    args = parser.parse_args()

    print("=" * 60)
    print("Cross-Server Data Migration")
    print("=" * 60)
    print(f"Source: {args.source_server} / {args.source_db}")
    print(f"Target: {args.target_server} / {args.target_db}")
    if args.dry_run:
        print("Mode:   DRY RUN")
    print()

    # Connect to both databases
    print("Connecting to source...")
    src_conn = get_connection(args.source_server, args.source_db)
    src_cursor = src_conn.cursor()
    print("  Connected")

    print("Connecting to target...")
    tgt_conn = get_connection(args.target_server, args.target_db)
    print("  Connected")

    # Migrate tables in FK order
    total = 0
    for table_name, id_column, columns in TABLES:
        count = migrate_table(src_cursor, tgt_conn, table_name, id_column, columns, args.dry_run)
        total += count

    # Verify
    if not args.dry_run and total > 0:
        tgt_cursor = tgt_conn.cursor()
        all_match = verify_counts(src_cursor, tgt_cursor)
        if all_match:
            print("\n  ALL COUNTS MATCH")
        else:
            print("\n  WARNING: Count mismatches detected — investigate before proceeding")

    # Summary
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"Total rows migrated: {total}")
    if args.dry_run:
        print("\n[DRY RUN] No changes were made.")

    src_conn.close()
    tgt_conn.close()


if __name__ == "__main__":
    main()
