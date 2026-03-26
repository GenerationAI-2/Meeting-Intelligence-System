"""OAuth 2.1 Authorization Server Provider for Meeting Intelligence.

Implements the MCP SDK's OAuthAuthorizationServerProvider Protocol to enable
per-user authentication on Claude Teams and ChatGPT org connectors (B17 fix).

Architecture: MI acts as its own OAuth Authorization Server. The consent page
asks users for their existing MI PAT token to prove identity. The JWT access
token's `sub` claim is set to the user's email (not the OAuth client_id),
which feeds into the existing RBAC pipeline unchanged.

SDK routes (/.well-known/*, /authorize, /token, /register, /revoke) are
mounted directly on the FastAPI app via create_auth_routes(). The /mcp
endpoint uses our custom middleware (not the SDK's BearerAuthBackend) so
PAT tokens continue to work alongside OAuth JWTs.
"""

import secrets
import time
from typing import Any

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


class MIOAuthProvider(OAuthAuthorizationServerProvider[MIAuthorizationCode, MIRefreshToken, MIAccessToken]):
    """OAuth 2.1 Authorization Server for Meeting Intelligence.

    In-memory storage for auth codes and refresh tokens (acceptable for
    single-replica deployments). OAuth clients and refresh tokens will
    be persisted to the control DB in a future iteration.
    """

    def __init__(self, jwt_secret: str, oauth_base_url: str):
        self._jwt_secret = jwt_secret
        self._oauth_base_url = oauth_base_url.rstrip("/")

        # In-memory stores (sufficient for single-replica; DB-backed later)
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._auth_codes: dict[str, MIAuthorizationCode] = {}
        self._refresh_tokens: dict[str, MIRefreshToken] = {}

        # Pending authorization sessions — maps session_id to AuthorizationParams + client
        # Used to bridge /authorize → /oauth/consent → redirect_uri
        self._pending_auth: dict[str, dict[str, Any]] = {}

    # ── Dynamic Client Registration (RFC 7591) ──────────────────────

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        client = self._clients.get(client_id)
        if client is None and client_id:
            # Auto-accept unknown client IDs (e.g. ChatGPT sends its own pre-assigned
            # client_id without DCR, or a previous DCR registration was lost on redeploy).
            # Security is enforced at the PAT consent step, not client registration.
            client = _PermissiveClient(
                client_id=client_id,
                client_name=f"Auto-registered ({client_id[:8]})",
                redirect_uris=["https://placeholder.invalid/callback"],
                scope="mcp",
                token_endpoint_auth_method="none",
            )
            self._clients[client_id] = client
            logger.info("OAuth client auto-registered: %s", client_id)
        return client

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if client_info.client_id in self._clients:
            raise RegistrationError(
                error="invalid_client_metadata",
                error_description="Client already registered",
            )
        self._clients[client_info.client_id] = client_info
        logger.info("OAuth client registered: %s (%s)", client_info.client_id, client_info.client_name)

    # ── Authorization ────────────────────────────────────────────────

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        """Start authorization flow — redirect to consent page.

        We save the authorization parameters in a pending session, then
        return a redirect URL to our consent page. The consent page will
        ask the user for their MI PAT to prove identity.
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

        return f"{self._oauth_base_url}/oauth/consent?session={session_id}"

    def complete_authorization(self, session_id: str, user_email: str) -> str:
        """Complete authorization after user consents — called by the consent endpoint.

        Creates an authorization code and returns the redirect URI with the code.
        """
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

        logger.info("OAuth tokens issued for user %s (client: %s)", user_email, client.client_id)

        return OAuthToken(
            access_token=access_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=refresh_token_str,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
        )

    # ── Refresh Token Exchange ───────────────────────────────────────

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> MIRefreshToken | None:
        token = self._refresh_tokens.get(refresh_token)
        if not token:
            return None
        if token.client_id != client.client_id:
            return None
        if token.expires_at and token.expires_at < int(time.time()):
            del self._refresh_tokens[refresh_token]
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

        logger.info("OAuth tokens refreshed for user %s (client: %s)", user_email, client.client_id)

        return OAuthToken(
            access_token=access_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=new_refresh_str,
            scope=" ".join(effective_scopes) if effective_scopes else None,
        )

    # ── Access Token Validation ──────────────────────────────────────

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

    # ── Token Revocation ─────────────────────────────────────────────

    async def revoke_token(self, token: MIAccessToken | MIRefreshToken) -> None:
        if isinstance(token, MIRefreshToken):
            # Revoke the refresh token and all tokens in the same family
            family_id = token.family_id
            to_remove = [k for k, v in self._refresh_tokens.items() if v.family_id == family_id]
            for k in to_remove:
                del self._refresh_tokens[k]
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
