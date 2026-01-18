"""Meeting Intelligence MCP Server - Database Connection"""

import struct
import pyodbc
from contextlib import contextmanager
from typing import Generator, Any
from azure.identity import DefaultAzureCredential
from .config import get_settings


def get_connection() -> pyodbc.Connection:
    """Create a new database connection using Entra ID token."""
    settings = get_settings()
    
    # Use standard Azure Credential (supports AZ CLI, Managed Identity, VS Code, etc.)
    credential = DefaultAzureCredential()
    
    # Get NEW token for every connection to handle expiry/refresh automatically
    # The DefaultAzureCredential caches the token internally and refreshes as needed,
    # so calling get_token() is performant and correct.
    token_bytes = credential.get_token("https://database.windows.net/.default").token.encode("UTF-16-LE")
    token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)
    
    # Connection string
    # Driver 18 requires encryption. TrustServerCertificate=no ensures we check the cert.
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={settings.azure_sql_server};"
        f"DATABASE={settings.azure_sql_database};"
        f"Encrypt=yes;TrustServerCertificate=no;"
    )
    
    # SQL_COPT_SS_ACCESS_TOKEN = 1256
    SQL_COPT_SS_ACCESS_TOKEN = 1256
    
    return pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})


@contextmanager
def get_db() -> Generator[pyodbc.Cursor, None, None]:
    """Context manager for database operations with auto-commit."""
    conn = get_connection()
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


def row_to_dict(cursor: pyodbc.Cursor, row: Any) -> dict:
    """Convert a pyodbc row to a dictionary."""
    if row is None:
        return None
    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row))


def rows_to_list(cursor: pyodbc.Cursor, rows: list) -> list[dict]:
    """Convert multiple pyodbc rows to a list of dictionaries."""
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in rows]
