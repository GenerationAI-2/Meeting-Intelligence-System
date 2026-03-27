"""OAuth 2.1 Authorization Server Provider for Meeting Intelligence.

Implements the MCP SDK's OAuthAuthorizationServerProvider Protocol to enable
per-user authentication on Claude Teams and ChatGPT org connectors (B17 fix).

Architecture: MI acts as an OAuth Authorization Server and proxies identity
to Azure AD. When Azure AD OAuth proxy is configured, /authorize redirects
to Azure AD login instead of the PAT consent page. Azure AD authenticates
the user, and the /oauth/callback endpoint exchanges the code for tokens,
extracts the user's email, and completes the MI OAuth flow. The JWT access
token's `sub` claim is set to the user's email (from Azure AD), which feeds
into the existing RBAC pipeline unchanged.

When Azure AD proxy is NOT configured, falls back to PAT consent page
(original Phase 1 behavior).

SDK routes (/.well-known/*, /authorize, /token, /register, /revoke) are
mounted directly on the FastAPI app via create_auth_routes(). The /mcp
endpoint uses our custom middleware (not the SDK's BearerAuthBackend) so
PAT tokens continue to work alongside OAuth JWTs.

Storage: OAuth clients and refresh tokens are persisted to the control DB
(OAuthClient and OAuthRefreshToken tables). In-memory dicts serve as
read-through caches. Auth codes and pending sessions are in-memory only
(ephemeral, <5 min TTL). If the control DB is unavailable, falls back to
in-memory-only mode with a warning log.
"""

import hashlib
import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import jwt
from pydantic import AnyHttpUrl, AnyUrl

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


class _PermissiveClient(OAuthClientInformationFull):
    """Client that accepts any redirect_uri (for auto-registered clients).

    ChatGPT and other AI clients may send their own client_id without DCR,
    or a previous DCR may have been lost on redeploy. Security is enforced
    at the PAT consent step, not at redirect_uri registration.
    """

    def validate_redirect_uri(self, redirect_uri: AnyUrl | None) -> AnyUrl:
        if redirect_uri is not None:
            return redirect_uri
        if self.redirect_uris and len(self.redirect_uris) == 1:
            return self.redirect_uris[0]
        from mcp.shared.auth import InvalidRedirectUriError
        raise InvalidRedirectUriError("redirect_uri is required")

from .logging_config import get_logger

logger = get_logger(__name__)

# Token lifetimes
ACCESS_TOKEN_TTL = 4 * 3600       # 4 hours (conservative; shorten if refresh works)
REFRESH_TOKEN_TTL = 30 * 86400    # 30 days
AUTH_CODE_TTL = 300                # 5 minutes


class MIAuthorizationCode(AuthorizationCode):
    """Extended auth code that carries the authenticated user's email."""
    user_email: str


class MIRefreshToken(RefreshToken):
    """Extended refresh token that carries the user's email and family ID."""
    user_email: str
    family_id: str  # For refresh token rotation / replay detection


class MIAccessToken(AccessToken):
    """Extended access token that carries the user's email."""
    user_email: str


# ── Database helpers ─────���────────────────────────────────────────────
# All DB operations are best-effort: if the control DB is unavailable,
# we log a warning and fall back to in-memory only. This ensures OAuth
# keeps working even during transient DB issues.

def _get_control_cursor():
    """Get a control DB context manager, or None if unavailable.

    Uses dynamic import to avoid the 'import mutable variable' gotcha
    (see CLAUDE.md — engine_registry is assigned at runtime).
    """
    try:
        from . import database as _db_module
        from .config import get_settings
        settings = get_settings()
        if not _db_module.engine_registry or not settings.control_db_name:
            return None
        eng = _db_module.engine_registry.get_engine(settings.control_db_name)
        from .database import get_db_for
        return get_db_for(eng)
    except Exception as e:
        logger.warning("OAuth DB access unavailable: %s", e)
        return None


def _db_save_client(client: OAuthClientInformationFull) -> None:
    """Persist an OAuth client registration to the control DB."""
    ctx = _get_control_cursor()
    if ctx is None:
        return
    try:
        with ctx as cursor:
            # Check if exists first (MERGE requires specific SQL Server syntax)
            cursor.execute("SELECT 1 FROM OAuthClient WHERE ClientId = ?", (client.client_id,))
            exists = cursor.fetchone() is not None

            redirect_uris_json = json.dumps([str(u) for u in (client.redirect_uris or [])])
            grant_types_json = json.dumps(client.grant_types or [])
            response_types_json = json.dumps(client.response_types or [])
            scope = client.scope or ""
            auth_method = client.token_endpoint_auth_method or "none"
            name = client.client_name or ""

            if exists:
                cursor.execute(
                    """
                    UPDATE OAuthClient SET
                        ClientName = ?, RedirectUris = ?, GrantTypes = ?,
                        ResponseTypes = ?, Scope = ?, TokenEndpointAuthMethod = ?, IsActive = 1
                    WHERE ClientId = ?
                    """,
                    (name, redirect_uris_json, grant_types_json,
                     response_types_json, scope, auth_method, client.client_id),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO OAuthClient
                        (ClientId, ClientName, ClientSecret, RedirectUris, GrantTypes,
                         ResponseTypes, Scope, TokenEndpointAuthMethod)
                    VALUES (?, ?, '', ?, ?, ?, ?, ?)
                    """,
                    (client.client_id, name, redirect_uris_json, grant_types_json,
                     response_types_json, scope, auth_method),
                )
    except Exception as e:
        logger.warning("Failed to persist OAuth client %s: %s", client.client_id, e)


def _db_load_client(client_id: str) -> OAuthClientInformationFull | None:
    """Load an OAuth client from the control DB."""
    ctx = _get_control_cursor()
    if ctx is None:
        return None
    try:
        with ctx as cursor:
            cursor.execute(
                """
                SELECT ClientId, ClientName, RedirectUris, GrantTypes,
                       ResponseTypes, Scope, TokenEndpointAuthMethod
                FROM OAuthClient
                WHERE ClientId = ? AND IsActive = 1
                """,
                (client_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            redirect_uris = json.loads(row[2]) if row[2] else ["https://placeholder.invalid/callback"]
            if not redirect_uris:
                redirect_uris = ["https://placeholder.invalid/callback"]
            return _PermissiveClient(
                client_id=row[0],
                client_name=row[1] or None,
                redirect_uris=redirect_uris,
                grant_types=json.loads(row[3]) if row[3] else None,
                response_types=json.loads(row[4]) if row[4] else None,
                scope=row[5] or "mcp",
                token_endpoint_auth_method=row[6] or "none",
            )
    except Exception as e:
        logger.warning("Failed to load OAuth client %s from DB: %s", client_id, e)
        return None


def _db_save_refresh_token(token: "MIRefreshToken") -> None:
    """Persist an active refresh token to the control DB."""
    ctx = _get_control_cursor()
    if ctx is None:
        return
    try:
        with ctx as cursor:
            cursor.execute(
                """
                INSERT INTO OAuthRefreshToken (Token, ClientId, UserEmail, Scopes, FamilyId, ExpiresAt)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    token.token,
                    token.client_id,
                    token.user_email,
                    json.dumps(token.scopes) if token.scopes else "[]",
                    token.family_id,
                    token.expires_at or 0,
                ),
            )
    except Exception as e:
        logger.warning("Failed to persist refresh token (family %s): %s", token.family_id, e)


def _db_load_refresh_token(token_str: str) -> "MIRefreshToken | None":
    """Load an active refresh token from the control DB."""
    ctx = _get_control_cursor()
    if ctx is None:
        return None
    try:
        with ctx as cursor:
            cursor.execute(
                """
                SELECT Token, ClientId, UserEmail, Scopes, FamilyId, ExpiresAt
                FROM OAuthRefreshToken
                WHERE Token = ?
                """,
                (token_str,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return MIRefreshToken(
                token=row[0],
                client_id=row[1],
                user_email=row[2],
                scopes=json.loads(row[3]) if row[3] else [],
                family_id=row[4],
                expires_at=row[5],
            )
    except Exception as e:
        logger.warning("Failed to load refresh token from DB: %s", e)
        return None


def _db_delete_refresh_token(token_str: str) -> None:
    """Delete a single refresh token from the control DB."""
    ctx = _get_control_cursor()
    if ctx is None:
        return
    try:
        with ctx as cursor:
            cursor.execute("DELETE FROM OAuthRefreshToken WHERE Token = ?", (token_str,))
    except Exception as e:
        logger.warning("Failed to delete refresh token from DB: %s", e)


def _db_revoke_family(family_id: str) -> None:
    """Revoke all refresh tokens in a family (theft detection)."""
    ctx = _get_control_cursor()
    if ctx is None:
        return
    try:
        with ctx as cursor:
            cursor.execute("DELETE FROM OAuthRefreshToken WHERE FamilyId = ?", (family_id,))
    except Exception as e:
        logger.warning("Failed to revoke token family %s from DB: %s", family_id, e)


def _db_log_consumed_token(token: "MIRefreshToken") -> None:
    """Log a consumed refresh token to RefreshTokenUsage for replay detection."""
    ctx = _get_control_cursor()
    if ctx is None:
        return
    try:
        token_hash = hashlib.sha256(token.token.encode()).hexdigest()
        with ctx as cursor:
            cursor.execute(
                """
                INSERT INTO RefreshTokenUsage (TokenHash, FamilyId, ClientId)
                VALUES (?, ?, ?)
                """,
                (token_hash, token.family_id, token.client_id),
            )
    except Exception as e:
        logger.warning("Failed to log consumed refresh token: %s", e)


# ── Provider ──────────────────────────────────────────────────────────

class MIOAuthProvider(OAuthAuthorizationServerProvider[MIAuthorizationCode, MIRefreshToken, MIAccessToken]):
    """OAuth 2.1 Authorization Server for Meeting Intelligence.

    In-memory caches backed by control DB persistence. Auth codes and pending
    sessions are in-memory only (short TTL, not worth persisting).
    Falls back to in-memory-only if control DB is unavailable.
    """

    def __init__(
        self,
        jwt_secret: str,
        oauth_base_url: str,
        azure_tenant_id: str = "",
        azure_client_id: str = "",
    ):
        self._jwt_secret = jwt_secret
        self._oauth_base_url = oauth_base_url.rstrip("/")

        # Azure AD proxy config (Phase 3)
        self._azure_tenant_id = azure_tenant_id
        self._azure_client_id = azure_client_id
        self._azure_ad_enabled = bool(azure_tenant_id and azure_client_id)

        # In-memory caches (read-through from DB)
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._refresh_tokens: dict[str, MIRefreshToken] = {}

        # In-memory only (ephemeral, short TTL)
        self._auth_codes: dict[str, MIAuthorizationCode] = {}
        self._pending_auth: dict[str, dict[str, Any]] = {}

    # ── Dynamic Client Registration (RFC 7591) ──────────────────────

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        # 1. In-memory cache
        client = self._clients.get(client_id)
        if client is not None:
            return client

        # 2. Read-through from DB
        client = _db_load_client(client_id)
        if client is not None:
            self._clients[client_id] = client
            logger.debug("OAuth client loaded from DB: %s", client_id)
            return client

        # 3. Auto-register unknown clients (ChatGPT, Claude send pre-assigned client_ids)
        if client_id:
            client = _PermissiveClient(
                client_id=client_id,
                client_name=f"Auto-registered ({client_id[:8]})",
                redirect_uris=["https://placeholder.invalid/callback"],
                scope="mcp",
                token_endpoint_auth_method="none",
            )
            self._clients[client_id] = client
            _db_save_client(client)
            logger.info("OAuth client auto-registered: %s", client_id)
            return client

        return None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        # Check in-memory first, then DB
        if client_info.client_id in self._clients:
            raise RegistrationError(
                error="invalid_client_metadata",
                error_description="Client already registered",
            )
        existing = _db_load_client(client_info.client_id)
        if existing is not None:
            # Already in DB — update in-memory cache and allow re-registration
            self._clients[client_info.client_id] = existing
            # Don't raise — just update the registration
            _db_save_client(client_info)
            self._clients[client_info.client_id] = client_info
            logger.info("OAuth client re-registered: %s (%s)", client_info.client_id, client_info.client_name)
            return

        self._clients[client_info.client_id] = client_info
        _db_save_client(client_info)
        logger.info("OAuth client registered: %s (%s)", client_info.client_id, client_info.client_name)

    # ── Authorization ────────────────────────────────────────────────

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        """Start authorization flow.

        When Azure AD proxy is configured: redirects to Azure AD login.
        Otherwise: redirects to PAT consent page (original behavior).

        We save the authorization parameters in a pending session keyed by
        session_id, which doubles as the `state` parameter for Azure AD.
        """
        session_id = secrets.token_urlsafe(32)
        self._pending_auth[session_id] = {
            "client": client,
            "params": params,
            "created_at": time.time(),
        }

        # Clean up expired sessions (>10 minutes old)
        cutoff = time.time() - 600
        expired = [k for k, v in self._pending_auth.items() if v["created_at"] < cutoff]
        for k in expired:
            del self._pending_auth[k]

        if self._azure_ad_enabled:
            # Redirect to Azure AD login — user authenticates there, then
            # Azure AD redirects back to /oauth/callback with code + state
            azure_params = urlencode({
                "client_id": self._azure_client_id,
                "response_type": "code",
                "redirect_uri": f"{self._oauth_base_url}/oauth/callback",
                "scope": "openid profile email",
                "state": session_id,
                "response_mode": "query",
                "prompt": "select_account",  # Force account picker — don't silently use SSO session
            })
            azure_url = (
                f"https://login.microsoftonline.com/{self._azure_tenant_id}"
                f"/oauth2/v2.0/authorize?{azure_params}"
            )
            logger.info("Azure AD proxy: redirecting to Azure AD for session %s", session_id[:8])
            return azure_url

        # Fallback: PAT consent page
        return f"{self._oauth_base_url}/oauth/consent?session={session_id}"

    def complete_authorization(self, session_id: str, user_email: str) -> str:
        """Complete authorization after user consents — called by the consent endpoint.

        Creates an authorization code and returns the redirect URI with the code.
        """
        user_email = user_email.lower()  # Normalize — JWT sub must match DB queries
        session = self._pending_auth.pop(session_id, None)
        if not session:
            raise ValueError("Invalid or expired authorization session")

        params: AuthorizationParams = session["params"]
        client: OAuthClientInformationFull = session["client"]

        # Generate authorization code (≥160 bits entropy per RFC 6749 §10.10)
        code = secrets.token_urlsafe(32)

        auth_code = MIAuthorizationCode(
            code=code,
            scopes=params.scopes or [],
            expires_at=time.time() + AUTH_CODE_TTL,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            user_email=user_email,
        )
        self._auth_codes[code] = auth_code

        # Build redirect URI with code and state
        redirect_params = {"code": code}
        if params.state:
            redirect_params["state"] = params.state

        return construct_redirect_uri(str(params.redirect_uri), **redirect_params)

    # ── Authorization Code Exchange ──────────────────────────────────

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> MIAuthorizationCode | None:
        code = self._auth_codes.get(authorization_code)
        if not code:
            return None
        if code.client_id != client.client_id:
            return None
        if code.expires_at < time.time():
            del self._auth_codes[authorization_code]
            return None
        return code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: MIAuthorizationCode
    ) -> OAuthToken:
        # Consume the code (one-time use)
        self._auth_codes.pop(authorization_code.code, None)

        now = int(time.time())
        user_email = authorization_code.user_email

        # Issue JWT access token with user email as subject
        access_payload = {
            "sub": user_email,
            "client_id": client.client_id,
            "scopes": authorization_code.scopes,
            "iat": now,
            "exp": now + ACCESS_TOKEN_TTL,
            "iss": self._oauth_base_url,
            "type": "access",
        }
        if authorization_code.resource:
            access_payload["resource"] = str(authorization_code.resource)

        access_token = jwt.encode(access_payload, self._jwt_secret, algorithm="HS256")

        # Issue refresh token
        family_id = secrets.token_urlsafe(16)
        refresh_token_str = secrets.token_urlsafe(32)
        refresh_obj = MIRefreshToken(
            token=refresh_token_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=now + REFRESH_TOKEN_TTL,
            user_email=user_email,
            family_id=family_id,
        )
        self._refresh_tokens[refresh_token_str] = refresh_obj
        _db_save_refresh_token(refresh_obj)

        logger.info("OAuth tokens issued for user %s (client: %s)", user_email, client.client_id)

        return OAuthToken(
            access_token=access_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=refresh_token_str,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
        )

    # ── Refresh Token Exchange ──────────���────────────────────────────

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> MIRefreshToken | None:
        # 1. In-memory cache
        token = self._refresh_tokens.get(refresh_token)

        # 2. Read-through from DB
        if token is None:
            token = _db_load_refresh_token(refresh_token)
            if token is not None:
                self._refresh_tokens[refresh_token] = token
                logger.debug("Refresh token loaded from DB (family %s)", token.family_id)

        if token is None:
            return None
        if token.client_id != client.client_id:
            return None
        if token.expires_at and token.expires_at < int(time.time()):
            self._refresh_tokens.pop(refresh_token, None)
            _db_delete_refresh_token(refresh_token)
            return None
        return token

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: MIRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        # Rotate: consume old refresh token, issue new pair
        self._refresh_tokens.pop(refresh_token.token, None)
        _db_delete_refresh_token(refresh_token.token)
        _db_log_consumed_token(refresh_token)

        now = int(time.time())
        user_email = refresh_token.user_email
        effective_scopes = scopes if scopes else refresh_token.scopes

        # New access token
        access_payload = {
            "sub": user_email,
            "client_id": client.client_id,
            "scopes": effective_scopes,
            "iat": now,
            "exp": now + ACCESS_TOKEN_TTL,
            "iss": self._oauth_base_url,
            "type": "access",
        }
        access_token = jwt.encode(access_payload, self._jwt_secret, algorithm="HS256")

        # New refresh token (same family for replay detection)
        new_refresh_str = secrets.token_urlsafe(32)
        new_refresh = MIRefreshToken(
            token=new_refresh_str,
            client_id=client.client_id,
            scopes=effective_scopes,
            expires_at=now + REFRESH_TOKEN_TTL,
            user_email=user_email,
            family_id=refresh_token.family_id,
        )
        self._refresh_tokens[new_refresh_str] = new_refresh
        _db_save_refresh_token(new_refresh)

        logger.info("OAuth tokens refreshed for user %s (client: %s)", user_email, client.client_id)

        return OAuthToken(
            access_token=access_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=new_refresh_str,
            scope=" ".join(effective_scopes) if effective_scopes else None,
        )

    # ── Access Token Validation ───────���──────────────────────────────

    async def load_access_token(self, token: str) -> MIAccessToken | None:
        """Validate a JWT access token and return access info."""
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=["HS256"])
        except jwt.InvalidTokenError:
            return None

        if payload.get("type") != "access":
            return None

        return MIAccessToken(
            token=token,
            client_id=payload.get("client_id", ""),
            scopes=payload.get("scopes", []),
            expires_at=payload.get("exp"),
            resource=payload.get("resource"),
            user_email=payload["sub"],
        )

    # ── Token Revocation ──────���────────────────────────────────────��─

    async def revoke_token(self, token: MIAccessToken | MIRefreshToken) -> None:
        if isinstance(token, MIRefreshToken):
            # Revoke the refresh token and all tokens in the same family
            family_id = token.family_id
            to_remove = [k for k, v in self._refresh_tokens.items() if v.family_id == family_id]
            for k in to_remove:
                del self._refresh_tokens[k]
            _db_revoke_family(family_id)
            logger.info("Revoked refresh token family %s", family_id)
        # Access tokens are JWTs — can't revoke without a blocklist.
        # They'll expire naturally (4hr TTL). Acceptable trade-off.

    # ── Consent Session Helpers ──────────────────────────────────────

    def get_pending_auth(self, session_id: str) -> dict | None:
        """Get pending authorization session (for consent page rendering)."""
        session = self._pending_auth.get(session_id)
        if not session:
            return None
        if session["created_at"] < time.time() - 600:
            del self._pending_auth[session_id]
            return None
        return session
