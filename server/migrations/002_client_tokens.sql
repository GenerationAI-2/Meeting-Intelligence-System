-- Migration 002: Client token management and OAuth persistence
-- Date: 2026-02-09
-- Stream: C (Auth Refactor)

-- === Client Token Table ===
-- Replaces MCP_AUTH_TOKENS environment variable
-- Supports expiry, revocation, rotation, and usage tracking

CREATE TABLE ClientToken (
    TokenId         INT IDENTITY(1,1) PRIMARY KEY,
    TokenHash       NVARCHAR(128)   NOT NULL UNIQUE,       -- SHA256 of plaintext token
    ClientName      NVARCHAR(128)   NOT NULL,              -- Human-readable client name
    ClientEmail     NVARCHAR(128)   NOT NULL,              -- Email for user attribution
    IsActive        BIT             NOT NULL DEFAULT 1,     -- 0 = revoked
    ExpiresAt       DATETIME2       NULL,                  -- NULL = never expires
    CreatedAt       DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
    CreatedBy       NVARCHAR(128)   NOT NULL,              -- Who created this token
    LastUsedAt      DATETIME2       NULL,                  -- Updated on each successful auth
    Notes           NVARCHAR(MAX)   NULL                   -- Admin notes (purpose, client contact, etc.)
);

-- Index for auth lookup (only active tokens)
CREATE INDEX IX_ClientToken_Hash ON ClientToken(TokenHash) WHERE IsActive = 1;

-- Index for admin listing by client
CREATE INDEX IX_ClientToken_Client ON ClientToken(ClientName);


-- === OAuth Client Table ===
-- Persists dynamic client registrations (currently in-memory)

CREATE TABLE OAuthClient (
    ClientId                NVARCHAR(255)   PRIMARY KEY,   -- OAuth client_id (UUID)
    ClientName              NVARCHAR(128)   NOT NULL,
    ClientSecret            NVARCHAR(255)   NOT NULL,      -- Hashed client secret
    RedirectUris            NVARCHAR(MAX)   NOT NULL,      -- JSON array of URIs
    GrantTypes              NVARCHAR(MAX)   NOT NULL,      -- JSON array
    ResponseTypes           NVARCHAR(MAX)   NOT NULL,      -- JSON array
    Scope                   NVARCHAR(MAX)   NULL,
    TokenEndpointAuthMethod NVARCHAR(50)    NOT NULL DEFAULT 'none',
    CreatedAt               DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
    IsActive                BIT             NOT NULL DEFAULT 1
);
