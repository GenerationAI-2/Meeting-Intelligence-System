"""Meeting Intelligence MCP Server - Database Connection

Provides connection pooling via SQLAlchemy QueuePool and retry logic
with exponential backoff for transient Azure SQL errors.

Pool configuration:
- pool_size=5, max_overflow=15 → total max 20 connections
- Azure SQL Basic tier limit: 30 connections (10 headroom)
- pool_pre_ping=True → detects stale connections after SQL auto-pause
- pool_recycle=1800 → recycle before Azure's 30-min idle kill
"""
from __future__ import annotations

import hashlib
import json
import secrets
import struct
import time
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Generator, Any, Optional

import pyodbc
pyodbc.pooling = False  # CRITICAL: disable pyodbc's hidden pool — conflicts with SQLAlchemy's pool

from azure.identity import DefaultAzureCredential
from sqlalchemy import create_engine, Engine
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


def call_with_retry(engine: Engine, func, *args,
                    max_retries: int = MAX_RETRIES,
                    base_delay: float = BASE_DELAY,
                    max_delay: float = MAX_DELAY, **kwargs):
    """Call func(cursor, *args, **kwargs) with a fresh cursor on each retry.

    Used by MCP handlers and API endpoints to wrap tool function calls.
    The cursor is acquired from the engine's pool and passed as the first arg.
    On transient errors, a new cursor is obtained and the call is retried.
    Non-transient errors (including HTTPException from permission checks)
    propagate immediately.
    """
    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            with get_db_for(engine) as cursor:
                return func(cursor, *args, **kwargs)
        except Exception as e:
            if not is_transient_error(e):
                raise
            last_exception = e
            if attempt == max_retries:
                logger.error(
                    "Tool call failed after %d attempts: %s",
                    attempt + 1, e, exc_info=True
                )
                return {
                    "error": True,
                    "code": "DATABASE_UNAVAILABLE",
                    "message": "Database temporarily unavailable. Please try again in a moment."
                }
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(
                "Transient error (attempt %d/%d): %s. Retrying in %.1fs",
                attempt + 1, max_retries + 1, e, delay
            )
            time.sleep(delay)
    raise last_exception  # Safety net


# ============================================================================
# ENGINE REGISTRY — Multi-database connection management
# ============================================================================

class EngineRegistry:
    """Thread-safe lazy engine cache. One engine per database on the same SQL Server."""

    def __init__(self, sql_server: str, pool_size: int = 3, max_overflow: int = 1):
        self._engines: dict[str, Engine] = {}
        self._lock = threading.Lock()
        self._sql_server = sql_server
        self._pool_size = pool_size
        self._max_overflow = max_overflow

    def get_engine(self, database_name: str) -> Engine:
        """Get or create an engine for the given database. Thread-safe, lazy."""
        if database_name in self._engines:
            return self._engines[database_name]
        with self._lock:
            if database_name not in self._engines:
                self._engines[database_name] = self._create_engine(database_name)
            return self._engines[database_name]

    def _create_engine(self, database_name: str) -> Engine:
        """Create a new SQLAlchemy engine for a specific database."""
        sql_server = self._sql_server

        def _connection_factory():
            credential = DefaultAzureCredential()
            token_bytes = credential.get_token(
                "https://database.windows.net/.default"
            ).token.encode("UTF-16-LE")
            token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)

            conn_str = (
                f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                f"SERVER={sql_server};"
                f"DATABASE={database_name};"
                f"Encrypt=yes;TrustServerCertificate=no;"
            )

            SQL_COPT_SS_ACCESS_TOKEN = 1256
            return pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})

        engine = create_engine(
            "mssql+pyodbc://",
            creator=_connection_factory,
            poolclass=QueuePool,
            pool_size=self._pool_size,
            max_overflow=self._max_overflow,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,
            pool_use_lifo=True,
        )
        logger.info(
            "Engine created for database '%s'",
            database_name,
            extra={
                "database": database_name,
                "pool_size": self._pool_size,
                "max_overflow": self._max_overflow,
            }
        )
        return engine

    def dispose_all(self) -> None:
        """Dispose all engines. Called on app shutdown."""
        with self._lock:
            for db_name, engine in self._engines.items():
                logger.info("Disposing engine for database '%s'", db_name)
                engine.dispose()
            self._engines.clear()

    @property
    def engine_count(self) -> int:
        return len(self._engines)


# Module-level singleton, initialised in main.py during app startup
engine_registry: Optional[EngineRegistry] = None


@contextmanager
def get_db_for(engine: Engine) -> Generator[pyodbc.Cursor, None, None]:
    """Yield a pyodbc cursor from a specific engine. Same pattern as get_db()."""
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
        conn.close()


@contextmanager
def get_control_db() -> Generator[pyodbc.Cursor, None, None]:
    """Shortcut: cursor for the control database."""
    settings = get_settings()
    if not engine_registry:
        raise RuntimeError("Engine registry not initialised — cannot access control database")
    if not settings.control_db_name:
        raise RuntimeError("CONTROL_DB_NAME not configured")
    eng = engine_registry.get_engine(settings.control_db_name)
    with get_db_for(eng) as cursor:
        yield cursor


def get_connection() -> pyodbc.Connection:
    """Create a new database connection using Entra ID token."""
    return _create_raw_connection()


@contextmanager
def get_db() -> Generator[pyodbc.Cursor, None, None]:
    """Context manager for database operations with auto-commit.

    Uses engine_registry when available (multi-database mode), falls back to
    legacy _get_engine() for backward compatibility (tests, stdio mode).
    """
    if engine_registry is not None:
        settings = get_settings()
        eng = engine_registry.get_engine(settings.azure_sql_database)
        with get_db_for(eng) as cursor:
            yield cursor
    else:
        # Legacy path — single global engine
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


# ============================================================================
# CLIENT TOKEN MANAGEMENT (DEPRECATED — use validate_token_from_control_db)
# These functions query the per-workspace ClientToken table.
# Kept for backward compatibility with deployments that have not yet migrated
# tokens to the control database. Will be removed in W4.
# ============================================================================

@retry_on_transient()
def validate_client_token(token_hash: str) -> dict | None:
    """Validate an MCP auth token against the workspace database.

    DEPRECATED: Use validate_token_from_control_db() when control_db_name is configured.
    Returns dict with {client_name, client_email} if valid, None if invalid/expired/revoked.
    Updates LastUsedAt on successful validation.
    """
    with get_db() as cursor:
        cursor.execute(
            """
            UPDATE ClientToken
            SET LastUsedAt = GETUTCDATE()
            OUTPUT inserted.ClientName, inserted.ClientEmail
            WHERE TokenHash = ?
              AND IsActive = 1
              AND (ExpiresAt IS NULL OR ExpiresAt > GETUTCDATE())
            """,
            (token_hash,)
        )
        row = cursor.fetchone()
        if row:
            return {"client_name": row[0], "client_email": row[1]}
        return None


@retry_on_transient()
def create_client_token(
    client_name: str,
    client_email: str,
    created_by: str,
    expires_days: int | None = None,
    notes: str | None = None,
) -> dict:
    """Generate a new client token and store its hash in workspace DB.

    DEPRECATED: New tokens should be created in the control database via manage_tokens.py.
    Returns dict with {token (plaintext — show ONCE), token_hash, client_name, expires_at}.
    """
    plaintext_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(plaintext_token.encode()).hexdigest()

    expires_at = None
    if expires_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

    with get_db() as cursor:
        cursor.execute(
            """
            INSERT INTO ClientToken (TokenHash, ClientName, ClientEmail, CreatedBy, ExpiresAt, Notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (token_hash, client_name, client_email, created_by, expires_at, notes)
        )

    return {
        "token": plaintext_token,
        "token_hash": token_hash,
        "client_name": client_name,
        "client_email": client_email,
        "expires_at": expires_at.isoformat() if expires_at else "never",
    }


@retry_on_transient()
def insert_token_hash(
    token_hash: str,
    client_name: str,
    client_email: str,
    created_by: str,
    notes: str | None = None,
) -> bool:
    """Insert a pre-computed token hash (used for migration from env var).

    DEPRECATED: Use control database tokens table via manage_tokens.py.
    """
    with get_db() as cursor:
        cursor.execute(
            """
            INSERT INTO ClientToken (TokenHash, ClientName, ClientEmail, CreatedBy, Notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (token_hash, client_name, client_email, created_by, notes)
        )
    return True


@retry_on_transient()
def revoke_client_token(token_id: int) -> bool:
    """Revoke a token by setting IsActive = 0.

    DEPRECATED: Use control database tokens table via manage_tokens.py.
    """
    with get_db() as cursor:
        cursor.execute(
            "UPDATE ClientToken SET IsActive = 0 WHERE TokenId = ?",
            (token_id,)
        )
        return cursor.rowcount > 0


@retry_on_transient()
def list_client_tokens() -> list[dict]:
    """List all tokens with metadata (NOT the hash — for admin display only).

    DEPRECATED: Use control database tokens table via manage_tokens.py or admin API.
    """
    with get_db() as cursor:
        cursor.execute(
            """
            SELECT TokenId, ClientName, ClientEmail, IsActive,
                   ExpiresAt, CreatedAt, CreatedBy, LastUsedAt, Notes
            FROM ClientToken
            ORDER BY CreatedAt DESC
            """
        )
        return rows_to_list(cursor, cursor.fetchall())


# ============================================================================
# CONTROL DB TOKEN VALIDATION
# ============================================================================

def validate_token_from_control_db(token_hash: str) -> dict | None:
    """Validate a token against the control database tokens table.

    Returns dict with full user + membership info if valid, None if invalid/expired
    or if the control database is not configured.

    Return shape:
    {
        "user_email": str,
        "is_org_admin": bool,
        "default_workspace_id": int | None,
        "memberships": [
            {
                "workspace_id": int,
                "workspace_name": str,
                "workspace_display_name": str,
                "db_name": str,
                "role": str,
                "is_default": bool,
                "is_archived": bool,
            },
            ...
        ]
    }
    """
    settings = get_settings()
    if not engine_registry or not settings.control_db_name:
        return None

    try:
        eng = engine_registry.get_engine(settings.control_db_name)
        with get_db_for(eng) as cursor:
            # Validate token and get user info in one query
            cursor.execute(
                """
                SELECT u.id, u.email, u.is_org_admin, u.default_workspace_id
                FROM tokens t
                JOIN users u ON u.id = t.user_id
                WHERE t.token_hash = ?
                  AND t.is_active = 1
                  AND (t.expires_at IS NULL OR t.expires_at > SYSUTCDATETIME())
                """,
                (token_hash,),
            )
            token_row = cursor.fetchone()
            if not token_row:
                return None

            user_id = token_row[0]
            user_email = token_row[1]
            is_org_admin = bool(token_row[2])
            default_workspace_id = token_row[3]

            # Get workspace memberships
            cursor.execute(
                """
                SELECT w.id, w.name, w.display_name, w.db_name, wm.role,
                       w.is_default, w.is_archived
                FROM workspace_members wm
                JOIN workspaces w ON w.id = wm.workspace_id
                WHERE wm.user_id = ?
                ORDER BY w.is_default DESC, w.name
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
            memberships = [
                {
                    "workspace_id": row[0],
                    "workspace_name": row[1],
                    "workspace_display_name": row[2],
                    "db_name": row[3],
                    "role": row[4],
                    "is_default": bool(row[5]),
                    "is_archived": bool(row[6]),
                }
                for row in rows
            ]

            return {
                "user_email": user_email,
                "is_org_admin": is_org_admin,
                "default_workspace_id": default_workspace_id,
                "memberships": memberships,
            }
    except Exception as e:
        logger.warning("Control DB token validation failed: %s", e)
        return None


# ============================================================================
# OAUTH CLIENT PERSISTENCE
# ============================================================================

@retry_on_transient()
def save_oauth_client(client_data: dict):
    """Persist an OAuth client registration to database."""
    with get_db() as cursor:
        cursor.execute(
            """
            MERGE INTO OAuthClient AS target
            USING (SELECT ? AS ClientId) AS source
            ON target.ClientId = source.ClientId
            WHEN MATCHED THEN UPDATE SET
                ClientName = ?,
                ClientSecret = ?,
                RedirectUris = ?,
                GrantTypes = ?,
                ResponseTypes = ?,
                Scope = ?,
                TokenEndpointAuthMethod = ?
            WHEN NOT MATCHED THEN INSERT
                (ClientId, ClientName, ClientSecret, RedirectUris, GrantTypes,
                 ResponseTypes, Scope, TokenEndpointAuthMethod)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                client_data["client_id"],
                # WHEN MATCHED (update)
                client_data.get("client_name", ""),
                client_data.get("client_secret", ""),
                json.dumps(client_data.get("redirect_uris", [])),
                json.dumps(client_data.get("grant_types", ["authorization_code"])),
                json.dumps(client_data.get("response_types", ["code"])),
                client_data.get("scope", ""),
                client_data.get("token_endpoint_auth_method", "none"),
                # WHEN NOT MATCHED (insert)
                client_data["client_id"],
                client_data.get("client_name", ""),
                client_data.get("client_secret", ""),
                json.dumps(client_data.get("redirect_uris", [])),
                json.dumps(client_data.get("grant_types", ["authorization_code"])),
                json.dumps(client_data.get("response_types", ["code"])),
                client_data.get("scope", ""),
                client_data.get("token_endpoint_auth_method", "none"),
            )
        )


@retry_on_transient()
def get_oauth_client(client_id: str) -> dict | None:
    """Retrieve an OAuth client registration from database."""
    with get_db() as cursor:
        cursor.execute(
            "SELECT * FROM OAuthClient WHERE ClientId = ? AND IsActive = 1",
            (client_id,)
        )
        row = cursor.fetchone()
        if row:
            return row_to_dict(cursor, row)
        return None


@retry_on_transient()
def load_all_oauth_clients() -> dict:
    """Load all active OAuth clients (for startup cache population).

    Returns dict keyed by client_id with lowercase keys matching the
    format used by the register endpoint in oauth.py.
    """
    with get_db() as cursor:
        cursor.execute("SELECT * FROM OAuthClient WHERE IsActive = 1")
        rows = cursor.fetchall()
        clients = {}
        for row in rows:
            d = row_to_dict(cursor, row)
            # Normalize to lowercase keys matching oauth.py register format
            client = {
                "client_id": d["ClientId"],
                "client_name": d.get("ClientName", ""),
                "client_secret": d.get("ClientSecret", ""),
                "redirect_uris": json.loads(d.get("RedirectUris", "[]")),
                "grant_types": json.loads(d.get("GrantTypes", "[]")),
                "response_types": json.loads(d.get("ResponseTypes", "[]")),
                "scope": d.get("Scope", ""),
                "token_endpoint_auth_method": d.get("TokenEndpointAuthMethod", "none"),
            }
            clients[client["client_id"]] = client
        return clients


# ============================================================================
# REFRESH TOKEN USAGE TRACKING (for OAuth 2.1 rotation)
# ============================================================================

@retry_on_transient()
def consume_refresh_token(token_hash: str, family_id: str, client_id: str) -> bool:
    """Record a refresh token as consumed. Returns False if already consumed (replay)."""
    with get_db() as cursor:
        # Clean up entries older than 35 days (covers 30-day token lifetime + buffer)
        cursor.execute(
            "DELETE FROM RefreshTokenUsage WHERE ConsumedAt < DATEADD(day, -35, GETUTCDATE())"
        )
        # Try to insert — if hash already exists, it's a replay
        try:
            cursor.execute(
                "INSERT INTO RefreshTokenUsage (TokenHash, FamilyId, ClientId) VALUES (?, ?, ?)",
                (token_hash, family_id, client_id)
            )
            return True
        except Exception:
            # Primary key violation = token already consumed
            return False


@retry_on_transient()
def revoke_token_family(family_id: str) -> int:
    """Revoke all tokens in a family (theft detection). Returns count deleted."""
    with get_db() as cursor:
        cursor.execute(
            "DELETE FROM RefreshTokenUsage WHERE FamilyId = ?",
            (family_id,)
        )
        return cursor.rowcount
