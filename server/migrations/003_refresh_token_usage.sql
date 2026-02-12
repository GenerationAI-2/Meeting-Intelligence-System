-- Migration 003: Refresh token usage tracking for rotation
-- Date: 2026-02-12
-- Purpose: Track consumed refresh tokens to enforce single-use (OAuth 2.1 rotation)

CREATE TABLE RefreshTokenUsage (
    TokenHash       NVARCHAR(128)   NOT NULL PRIMARY KEY,  -- SHA256 of JWT refresh token
    FamilyId        NVARCHAR(128)   NOT NULL,              -- Token family for theft detection
    ClientId        NVARCHAR(255)   NOT NULL,              -- OAuth client that used this token
    ConsumedAt      DATETIME2       NOT NULL DEFAULT GETUTCDATE()
);

-- Index for cleanup of expired entries (tokens older than 30 days)
CREATE INDEX IX_RefreshTokenUsage_ConsumedAt ON RefreshTokenUsage(ConsumedAt);

-- Index for family-based revocation (if a replayed token is detected)
CREATE INDEX IX_RefreshTokenUsage_FamilyId ON RefreshTokenUsage(FamilyId);
