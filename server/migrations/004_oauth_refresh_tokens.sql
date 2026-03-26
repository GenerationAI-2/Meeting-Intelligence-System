-- Migration 004: Active OAuth refresh token storage
-- Date: 2026-03-27
-- Purpose: Persist active refresh tokens so they survive container restarts.
--          RefreshTokenUsage (003) tracks *consumed* tokens for replay detection.
--          This table stores *active* tokens for lookup during token exchange.

CREATE TABLE OAuthRefreshToken (
    Token           NVARCHAR(255)   NOT NULL PRIMARY KEY,  -- Plaintext refresh token string (lookup key)
    ClientId        NVARCHAR(255)   NOT NULL,              -- OAuth client that owns this token
    UserEmail       NVARCHAR(255)   NOT NULL,              -- User identity (lowercase)
    Scopes          NVARCHAR(MAX)   NULL,                  -- JSON array of granted scopes
    FamilyId        NVARCHAR(128)   NOT NULL,              -- Token family for rotation/theft detection
    ExpiresAt       BIGINT          NOT NULL,              -- Unix timestamp
    CreatedAt       DATETIME2       NOT NULL DEFAULT GETUTCDATE()
);

-- Cleanup of expired tokens (tokens older than 30 days)
CREATE INDEX IX_OAuthRefreshToken_ExpiresAt ON OAuthRefreshToken(ExpiresAt);

-- Family-based revocation (revoke all tokens in a family on theft detection)
CREATE INDEX IX_OAuthRefreshToken_FamilyId ON OAuthRefreshToken(FamilyId);

-- User lookup (list active sessions for a user)
CREATE INDEX IX_OAuthRefreshToken_UserEmail ON OAuthRefreshToken(UserEmail);
