# ChatGPT OAuth Implementation Prompt

**For:** Developer agent implementing OAuth 2.1 for ChatGPT MCP support

**Date:** 4 February 2026

---

## Context

ChatGPT supports MCP but requires **OAuth 2.1 with PKCE and Dynamic Client Registration**. Our current token-based auth won't work with ChatGPT.

We already have:
- ✅ Streamable HTTP transport (`/mcp`) — works with ChatGPT
- ✅ SSE transport (`/sse`) — works with Claude
- ✅ Path-based token auth — works with Copilot
- ❌ OAuth 2.1 — **needed for ChatGPT**

**Full implementation spec:** `docs/chatgpt-oauth-implementation.md`

---

## Task

Implement OAuth 2.1 authorization server on the **team instance only**.

### Requirements

1. **Well-known metadata endpoints**
   - `GET /.well-known/oauth-protected-resource`
   - `GET /.well-known/oauth-authorization-server`

2. **Dynamic Client Registration** (RFC 7591)
   - `POST /oauth/register`

3. **Authorization endpoint with PKCE**
   - `GET /oauth/authorize`
   - S256 code challenge validation

4. **Token endpoint**
   - `POST /oauth/token`
   - Authorization code grant
   - Refresh token grant
   - PKCE code_verifier validation

5. **Update MCP auth middleware**
   - Accept OAuth Bearer tokens (for ChatGPT)
   - Keep existing token auth (for Claude/Copilot)

### Recommended Approach

Use **authlib** library for RFC-compliant implementation:

```bash
pip install authlib
```

Or implement manually following the spec in `docs/chatgpt-oauth-implementation.md`.

### Key Files

- `server/src/main.py` — Add OAuth endpoints here
- `server/src/api.py` — Or here if separating concerns
- `server/requirements.txt` — Add authlib

---

## Deployment

**IMPORTANT:** Deploy to **team instance only**

```bash
./deploy.sh team
```

**Do NOT deploy to prod** until ChatGPT integration is validated.

---

## Testing

### 1. Metadata endpoints

```bash
curl https://meeting-intelligence-team.happystone-42529ebe.australiaeast.azurecontainerapps.io/.well-known/oauth-protected-resource

curl https://meeting-intelligence-team.happystone-42529ebe.australiaeast.azurecontainerapps.io/.well-known/oauth-authorization-server
```

### 2. Client registration

```bash
curl -X POST https://meeting-intelligence-team.../oauth/register \
  -H "Content-Type: application/json" \
  -d '{"redirect_uris": ["https://chat.openai.com/callback"]}'
```

### 3. ChatGPT Developer Mode

1. Open ChatGPT → Settings → Apps & Connectors → Advanced Settings
2. Enable Developer Mode
3. Click "Add MCP Server"
4. Enter team instance URL
5. Complete OAuth flow
6. Test: "List my recent meetings"

### 4. Verify no regression

```bash
# Claude SSE still works
curl https://meeting-intelligence-team.../sse?token=YOUR_TOKEN

# Copilot Streamable HTTP still works
curl -X POST https://meeting-intelligence-team.../mcp/YOUR_TOKEN \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

---

## Definition of Done

- [ ] Well-known endpoints return valid metadata
- [ ] ChatGPT can register as client
- [ ] ChatGPT can complete OAuth flow
- [ ] ChatGPT can list and execute tools
- [ ] Claude still works (SSE + token auth)
- [ ] Copilot still works (Streamable HTTP + path token)

---

## Out of Scope

- Database storage for OAuth (in-memory OK for MVP)
- Fancy consent screen UI
- Prod deployment
- Token revocation

---

## Environment Variables

Add to `.env.deploy`:

```
JWT_SECRET=<generate-secure-random-string>
```

---

*If blocked, check `docs/chatgpt-oauth-implementation.md` or ask Caleb.*
