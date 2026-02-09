# ChatGPT OAuth 2.1 Implementation

**Purpose:** Add ChatGPT support by implementing OAuth 2.1 with PKCE and Dynamic Client Registration.

**Status:** Research complete, ready for implementation

**Target:** Team instance only (`meeting-intelligence-team`)

**Effort estimate:** 2-4 days

> ⚠️ **Do NOT deploy to prod** until tested end-to-end in ChatGPT

---

## Why OAuth is Required

ChatGPT's MCP client **mandates OAuth 2.1** for authenticated servers. Our current token-based auth (query param/path) won't work.

| Current State | ChatGPT Requirement | Gap |
|--------------|---------------------|-----|
| Token in query param/path | OAuth 2.1 Bearer header | **Critical** |
| No OAuth metadata | `/.well-known/*` endpoints | **Critical** |
| No DCR support | Dynamic Client Registration | **Critical** |
| No PKCE | S256 code challenge | **Critical** |
| Streamable HTTP ✅ | Streamable HTTP preferred | Already done |

---

## Required Endpoints

### 1. Protected Resource Metadata
`GET /.well-known/oauth-protected-resource`

```json
{
  "resource": "https://meeting-intelligence-team.happystone-42529ebe.australiaeast.azurecontainerapps.io",
  "authorization_servers": ["https://meeting-intelligence-team.happystone-42529ebe.australiaeast.azurecontainerapps.io"],
  "scopes_supported": ["mcp:read", "mcp:write"],
  "bearer_methods_supported": ["header"]
}
```

### 2. Authorization Server Metadata
`GET /.well-known/oauth-authorization-server`

```json
{
  "issuer": "https://meeting-intelligence-team.happystone-42529ebe.australiaeast.azurecontainerapps.io",
  "authorization_endpoint": "/oauth/authorize",
  "token_endpoint": "/oauth/token",
  "registration_endpoint": "/oauth/register",
  "scopes_supported": ["mcp:read", "mcp:write"],
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "code_challenge_methods_supported": ["S256"]
}
```

### 3. Dynamic Client Registration (RFC 7591)
`POST /oauth/register`

ChatGPT registers itself as a client before initiating auth flow.

### 4. Authorization Endpoint
`GET /oauth/authorize`

Shows consent screen, validates PKCE code_challenge.

### 5. Token Endpoint
`POST /oauth/token`

Exchanges authorization code for access/refresh tokens, validates code_verifier.

---

## Implementation Plan

### Phase 1: Metadata Endpoints (2-4 hours)

Add well-known endpoints to FastAPI:

```python
@app.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource():
    base_url = "https://meeting-intelligence-team.happystone-42529ebe.australiaeast.azurecontainerapps.io"
    return {
        "resource": base_url,
        "authorization_servers": [base_url],
        "scopes_supported": ["mcp:read", "mcp:write"],
        "bearer_methods_supported": ["header"]
    }

@app.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server():
    base_url = "https://meeting-intelligence-team.happystone-42529ebe.australiaeast.azurecontainerapps.io"
    return {
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/oauth/authorize",
        "token_endpoint": f"{base_url}/oauth/token",
        "registration_endpoint": f"{base_url}/oauth/register",
        "scopes_supported": ["mcp:read", "mcp:write"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"]
    }
```

### Phase 2: Dynamic Client Registration (4-6 hours)

```python
from pydantic import BaseModel
import secrets
import uuid

class ClientRegistrationRequest(BaseModel):
    redirect_uris: list[str]
    client_name: str | None = None
    scope: str | None = None

# Store in database for production (in-memory for MVP)
registered_clients = {}

@app.post("/oauth/register")
async def register_client(request: ClientRegistrationRequest):
    client_id = str(uuid.uuid4())
    client_secret = secrets.token_urlsafe(32)

    registered_clients[client_id] = {
        "client_secret": client_secret,
        "redirect_uris": request.redirect_uris,
        "client_name": request.client_name or "ChatGPT",
        "created_at": datetime.utcnow().isoformat()
    }

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uris": request.redirect_uris
    }
```

### Phase 3: Authorization Endpoint with PKCE (4-6 hours)

```python
import hashlib
import base64

# Store pending auth codes
pending_auth_codes = {}

@app.get("/oauth/authorize")
async def authorize(
    response_type: str,
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str,
    code_challenge: str,
    code_challenge_method: str = "S256"
):
    # Validate client exists
    if client_id not in registered_clients:
        raise HTTPException(400, "Invalid client_id")

    # Validate redirect_uri
    client = registered_clients[client_id]
    if redirect_uri not in client["redirect_uris"]:
        raise HTTPException(400, "Invalid redirect_uri")

    # For MVP: auto-approve (production: show consent screen)
    auth_code = secrets.token_urlsafe(32)
    pending_auth_codes[auth_code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "expires_at": datetime.utcnow() + timedelta(minutes=10)
    }

    # Redirect back with code
    return RedirectResponse(f"{redirect_uri}?code={auth_code}&state={state}")
```

### Phase 4: Token Endpoint (4-6 hours)

```python
import jwt
from datetime import datetime, timedelta

JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_urlsafe(32))

@app.post("/oauth/token")
async def token(
    grant_type: str = Form(...),
    code: str = Form(None),
    redirect_uri: str = Form(None),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    code_verifier: str = Form(None),
    refresh_token: str = Form(None)
):
    # Validate client credentials
    if client_id not in registered_clients:
        raise HTTPException(401, "Invalid client")
    if registered_clients[client_id]["client_secret"] != client_secret:
        raise HTTPException(401, "Invalid client_secret")

    if grant_type == "authorization_code":
        # Validate auth code
        if code not in pending_auth_codes:
            raise HTTPException(400, "Invalid code")

        auth = pending_auth_codes[code]

        # Validate PKCE
        verifier_hash = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip("=")

        if verifier_hash != auth["code_challenge"]:
            raise HTTPException(400, "Invalid code_verifier")

        # Clean up used code
        del pending_auth_codes[code]

        # Generate tokens
        access_token = jwt.encode({
            "sub": client_id,
            "scope": auth["scope"],
            "exp": datetime.utcnow() + timedelta(hours=1)
        }, JWT_SECRET, algorithm="HS256")

        refresh = jwt.encode({
            "sub": client_id,
            "type": "refresh",
            "exp": datetime.utcnow() + timedelta(days=30)
        }, JWT_SECRET, algorithm="HS256")

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": refresh,
            "scope": auth["scope"]
        }

    elif grant_type == "refresh_token":
        # Validate and issue new tokens
        try:
            payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=["HS256"])
            # Issue new access token
            access_token = jwt.encode({
                "sub": payload["sub"],
                "scope": "mcp:read mcp:write",
                "exp": datetime.utcnow() + timedelta(hours=1)
            }, JWT_SECRET, algorithm="HS256")

            return {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600
            }
        except jwt.ExpiredSignatureError:
            raise HTTPException(401, "Refresh token expired")

    raise HTTPException(400, "Unsupported grant_type")
```

### Phase 5: Token Validation Middleware (2-4 hours)

Update MCP endpoint auth to accept both:
- Existing token auth (for Claude)
- OAuth Bearer tokens (for ChatGPT)

```python
async def validate_mcp_auth(request: Request):
    # Check for OAuth Bearer token first
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            return {"type": "oauth", "client_id": payload["sub"]}
        except jwt.InvalidTokenError:
            pass

    # Fall back to existing token auth (for Claude)
    token = request.query_params.get("token")
    if token and token in valid_tokens:
        return {"type": "token", "token": token}

    # Check path-based token (for Copilot)
    # ... existing path token logic

    raise HTTPException(401, "Unauthorized")
```

---

## Recommended Library: authlib

For production, use **authlib** instead of manual implementation:

```bash
pip install authlib
```

Authlib provides:
- RFC-compliant OAuth 2.1 server
- Built-in PKCE support
- Dynamic Client Registration (RFC 7591)
- JWT handling

---

## Testing

### 1. Test metadata endpoints

```bash
curl https://meeting-intelligence-team.../well-known/oauth-protected-resource
curl https://meeting-intelligence-team.../.well-known/oauth-authorization-server
```

### 2. Test client registration

```bash
curl -X POST https://meeting-intelligence-team.../oauth/register \
  -H "Content-Type: application/json" \
  -d '{"redirect_uris": ["https://chat.openai.com/callback"], "client_name": "Test"}'
```

### 3. Test in ChatGPT

1. Enable Developer Mode: Settings → Apps & Connectors → Advanced Settings
2. Click "Add MCP Server"
3. Enter: `https://meeting-intelligence-team.happystone-42529ebe.australiaeast.azurecontainerapps.io`
4. Complete OAuth flow
5. Test: "List my recent meetings"

---

## Storage Considerations

**MVP (in-memory):**
- Quick to implement
- Data lost on restart
- Fine for testing

**Production (database):**
- Add `OAuthClient` table for registered clients
- Add `OAuthToken` table for refresh tokens
- Add `OAuthAuthCode` table for pending auth codes (with TTL)

---

## Deployment Checklist

- [ ] Add `authlib` to requirements.txt (or implement manually)
- [ ] Add `JWT_SECRET` to environment variables
- [ ] Implement `/.well-known/oauth-protected-resource`
- [ ] Implement `/.well-known/oauth-authorization-server`
- [ ] Implement `/oauth/register`
- [ ] Implement `/oauth/authorize`
- [ ] Implement `/oauth/token`
- [ ] Update MCP auth middleware to accept Bearer tokens
- [ ] Test locally with curl
- [ ] Deploy to team instance
- [ ] Test in ChatGPT Developer Mode
- [ ] Document results

---

## Definition of Done

- [ ] ChatGPT can discover server via well-known endpoints
- [ ] ChatGPT can register as OAuth client
- [ ] ChatGPT can complete OAuth flow
- [ ] ChatGPT can list tools
- [ ] ChatGPT can execute at least one tool
- [ ] Claude still works (no regression)
- [ ] Copilot still works (no regression)

---

## Out of Scope

- Production OAuth storage (database tables)
- User consent screen UI (auto-approve for MVP)
- Token revocation endpoint
- Prod deployment

---

*If blocked, check the research doc or ask Caleb.*
