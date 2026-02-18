-- ============================================================
-- Database Setup Script for testing-instance
-- Run in Azure Portal Query Editor against: mi-testing-instance
-- SQL Server: mi-testing-instance-sql.database.windows.net
-- ============================================================
-- Run each section separately (Azure Portal Query Editor
-- doesn't support GO batch separators well)

-- SECTION 1: Initial Schema (from schema.sql)
-- ============================================================
CREATE TABLE Meeting (
    MeetingId INT IDENTITY(1,1) PRIMARY KEY,
    Title NVARCHAR(255) NOT NULL,
    MeetingDate DATETIME2 NOT NULL,
    RawTranscript NVARCHAR(MAX),
    Summary NVARCHAR(MAX),
    Attendees NVARCHAR(MAX),
    Source NVARCHAR(50) DEFAULT 'Manual',
    SourceMeetingId NVARCHAR(255),
    Tags NVARCHAR(MAX),
    CreatedAt DATETIME2 DEFAULT GETUTCDATE(),
    CreatedBy NVARCHAR(128) NOT NULL,
    UpdatedAt DATETIME2 DEFAULT GETUTCDATE(),
    UpdatedBy NVARCHAR(128) NOT NULL
);

CREATE INDEX IX_Meeting_MeetingDate ON Meeting(MeetingDate DESC);
CREATE INDEX IX_Meeting_SourceMeetingId ON Meeting(SourceMeetingId);

CREATE TABLE Decision (
    DecisionId INT IDENTITY(1,1) PRIMARY KEY,
    MeetingId INT NOT NULL,
    DecisionText NVARCHAR(MAX) NOT NULL,
    Context NVARCHAR(MAX),
    CreatedAt DATETIME2 DEFAULT GETUTCDATE(),
    CreatedBy NVARCHAR(128) NOT NULL,
    CONSTRAINT FK_Decision_Meeting FOREIGN KEY (MeetingId) REFERENCES Meeting(MeetingId)
);

CREATE INDEX IX_Decision_MeetingId ON Decision(MeetingId);

CREATE TABLE Action (
    ActionId INT IDENTITY(1,1) PRIMARY KEY,
    MeetingId INT,
    ActionText NVARCHAR(MAX) NOT NULL,
    Owner NVARCHAR(128) NOT NULL,
    DueDate DATE,
    Status NVARCHAR(20) DEFAULT 'Open' CHECK (Status IN ('Open', 'Complete', 'Parked')),
    Notes NVARCHAR(MAX),
    CreatedAt DATETIME2 DEFAULT GETUTCDATE(),
    CreatedBy NVARCHAR(128) NOT NULL,
    UpdatedAt DATETIME2 DEFAULT GETUTCDATE(),
    UpdatedBy NVARCHAR(128) NOT NULL,
    CONSTRAINT FK_Action_Meeting FOREIGN KEY (MeetingId) REFERENCES Meeting(MeetingId)
);

CREATE INDEX IX_Action_Status ON Action(Status);
CREATE INDEX IX_Action_Owner ON Action(Owner);
CREATE INDEX IX_Action_DueDate ON Action(DueDate);
CREATE INDEX IX_Action_MeetingId ON Action(MeetingId);

-- SECTION 2: Migration 002 - Client Tokens + OAuth (from 002_client_tokens.sql)
-- ============================================================
CREATE TABLE ClientToken (
    TokenId         INT IDENTITY(1,1) PRIMARY KEY,
    TokenHash       NVARCHAR(128)   NOT NULL UNIQUE,
    ClientName      NVARCHAR(128)   NOT NULL,
    ClientEmail     NVARCHAR(128)   NOT NULL,
    IsActive        BIT             NOT NULL DEFAULT 1,
    ExpiresAt       DATETIME2       NULL,
    CreatedAt       DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
    CreatedBy       NVARCHAR(128)   NOT NULL,
    LastUsedAt      DATETIME2       NULL,
    Notes           NVARCHAR(MAX)   NULL
);

CREATE INDEX IX_ClientToken_Hash ON ClientToken(TokenHash) WHERE IsActive = 1;
CREATE INDEX IX_ClientToken_Client ON ClientToken(ClientName);

CREATE TABLE OAuthClient (
    ClientId                NVARCHAR(255)   PRIMARY KEY,
    ClientName              NVARCHAR(128)   NOT NULL,
    ClientSecret            NVARCHAR(255)   NOT NULL,
    RedirectUris            NVARCHAR(MAX)   NOT NULL,
    GrantTypes              NVARCHAR(MAX)   NOT NULL,
    ResponseTypes           NVARCHAR(MAX)   NOT NULL,
    Scope                   NVARCHAR(MAX)   NULL,
    TokenEndpointAuthMethod NVARCHAR(50)    NOT NULL DEFAULT 'none',
    CreatedAt               DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
    IsActive                BIT             NOT NULL DEFAULT 1
);

-- SECTION 3: Migration 003 - Refresh Token Usage (from 003_refresh_token_usage.sql)
-- ============================================================
CREATE TABLE RefreshTokenUsage (
    TokenHash       NVARCHAR(128)   NOT NULL PRIMARY KEY,
    FamilyId        NVARCHAR(128)   NOT NULL,
    ClientId        NVARCHAR(255)   NOT NULL,
    ConsumedAt      DATETIME2       NOT NULL DEFAULT GETUTCDATE()
);

CREATE INDEX IX_RefreshTokenUsage_ConsumedAt ON RefreshTokenUsage(ConsumedAt);
CREATE INDEX IX_RefreshTokenUsage_FamilyId ON RefreshTokenUsage(FamilyId);

-- SECTION 4: Migration Tracking Table
-- ============================================================
CREATE TABLE _MigrationHistory (
    MigrationId     NVARCHAR(255)   NOT NULL PRIMARY KEY,
    AppliedAt       DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
    AppliedBy       NVARCHAR(128)   NOT NULL,
    Checksum        NVARCHAR(64)    NOT NULL
);

INSERT INTO _MigrationHistory (MigrationId, AppliedBy, Checksum)
VALUES ('002_client_tokens', 'manual-deploy', '93027b758c2792a1');

INSERT INTO _MigrationHistory (MigrationId, AppliedBy, Checksum)
VALUES ('003_refresh_token_usage', 'manual-deploy', '5f3ebce8c2ef3609');

-- SECTION 5: Managed Identity Database User
-- ============================================================
CREATE USER [mi-testing-instance] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [mi-testing-instance];
ALTER ROLE db_datawriter ADD MEMBER [mi-testing-instance];

-- SECTION 6: Insert Auth Token
-- ============================================================
INSERT INTO ClientToken (TokenHash, ClientName, ClientEmail, IsActive, CreatedBy, Notes)
VALUES ('11b365f06b8622f6e5f21c9e2bf4a1c570ed8414aa7ec74291de9d70a3d88a02', 'Testing Instance - Caleb', 'caleb.lucas@generationai.co.nz', 1, 'deploy', 'Initial token for testing-instance deployment');

-- SECTION 7: Verify
-- ============================================================
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES ORDER BY TABLE_NAME;
