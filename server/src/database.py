"""Meeting Intelligence MCP Server - Database Connection

Provides connection pooling via SQLAlchemy QueuePool and retry logic
with exponential backoff for transient Azure SQL errors.

Pool configuration:
- pool_size=5, max_overflow=15 → total max 20 connections
- Azure SQL Basic tier limit: 30 connections (10 headroom)
- pool_pre_ping=True → detects stale connections after SQL auto-pause
- pool_recycle=1800 → recycle before Azure's 30-min idle kill
"""

import struct
import time
import logging
from contextlib import contextmanager
from functools import wraps
from typing import Generator, Any

import pyodbc
from azure.identity import DefaultAzureCredential
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

from .config import get_settings

logger = logging.getLogger(__name__)

# Azure SQL transient error codes
TRANSIENT_SQL_ERRORS = {
    "08S01",   # Communication link failure
    "08001",   # Unable to connect to server
    "40613",   # Database not currently available (auto-pause resume)
    "40197",   # Service error processing request
    "40501",   # Service busy
    "49918",   # Not enough resources
    "49919",   # Cannot process request — not enough resources
    "49920",   # Too many requests
    "4060",    # Cannot open database (during failover)
    "40001",   # Deadlock victim
    "10054",   # Connection forcibly closed (TCP reset)
    "10053",   # Connection abort by software
    "233",     # Connection does not exist
}

# Pool configuration — Azure SQL Basic tier has 30-connection limit
POOL_SIZE = 5           # Base connections to keep open
MAX_OVERFLOW = 15       # Extra connections under load (total max: 20)
POOL_TIMEOUT = 30       # Seconds to wait for connection from pool
POOL_RECYCLE = 1800     # Recycle connections every 30 minutes

# Retry configuration
MAX_RETRIES = 3
BASE_DELAY = 0.5        # seconds
MAX_DELAY = 10.0        # seconds

# Module-level engine (lazy init)
_engine = None


def _create_raw_connection() -> pyodbc.Connection:
    """Create a raw pyodbc connection with Azure AD token auth."""
    settings = get_settings()

    credential = DefaultAzureCredential()
    token_bytes = credential.get_token(
        "https://database.windows.net/.default"
    ).token.encode("UTF-16-LE")
    token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)

    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={settings.azure_sql_server};"
        f"DATABASE={settings.azure_sql_database};"
        f"Encrypt=yes;TrustServerCertificate=no;"
    )

    SQL_COPT_SS_ACCESS_TOKEN = 1256
    return pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})


def _get_engine():
    """Get or create the SQLAlchemy engine with connection pooling."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            "mssql+pyodbc://",
            creator=_create_raw_connection,
            poolclass=QueuePool,
            pool_size=POOL_SIZE,
            max_overflow=MAX_OVERFLOW,
            pool_timeout=POOL_TIMEOUT,
            pool_recycle=POOL_RECYCLE,
            pool_pre_ping=True,
        )
        logger.info(
            "Database pool configured",
            extra={
                "pool_size": POOL_SIZE,
                "max_overflow": MAX_OVERFLOW,
                "max_total": POOL_SIZE + MAX_OVERFLOW,
                "sql_tier_limit": 30,
                "pool_recycle": POOL_RECYCLE,
                "pool_pre_ping": True,
            }
        )
    return _engine


def is_transient_error(exception: Exception) -> bool:
    """Check if a database error is transient and worth retrying."""
    error_str = str(exception)
    return any(code in error_str for code in TRANSIENT_SQL_ERRORS)


def retry_on_transient(max_retries: int = MAX_RETRIES, base_delay: float = BASE_DELAY, max_delay: float = MAX_DELAY):
    """
    Retry on transient SQL errors with exponential backoff.

    Delays: 0.5s -> 1.0s -> 2.0s (capped at max_delay).
    After all retries exhaust, returns a graceful error dict so MCP clients
    never see stack traces.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if not is_transient_error(e):
                        raise  # Non-transient errors pass through immediately
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(
                            "Database operation failed after %d attempts: %s",
                            attempt + 1, e, exc_info=True
                        )
                        return {
                            "error": True,
                            "code": "DATABASE_UNAVAILABLE",
                            "message": "Database temporarily unavailable. Please try again in a moment."
                        }
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(
                        "Transient database error (attempt %d/%d): %s: %s. Retrying in %.1fs",
                        attempt + 1, max_retries + 1, type(e).__name__, e, delay
                    )
                    time.sleep(delay)
            raise last_exception  # Safety net
        return wrapper
    return decorator


def get_connection() -> pyodbc.Connection:
    """Create a new database connection using Entra ID token."""
    return _create_raw_connection()


@contextmanager
def get_db() -> Generator[pyodbc.Cursor, None, None]:
    """Context manager for database operations with auto-commit.

    Uses SQLAlchemy connection pool for efficient connection reuse.
    pool_pre_ping detects stale connections (e.g., after SQL auto-pause).
    """
    engine = _get_engine()
    conn = engine.raw_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()  # Returns connection to pool (not a real close)


def test_connection() -> bool:
    """Test database connectivity for health probes."""
    with get_db() as cursor:
        cursor.execute("SELECT 1")
        return True


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
