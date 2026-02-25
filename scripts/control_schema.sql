-- =============================================================================
-- MI Control Database Schema
-- Run against: {client}-mi-control database on the client's SQL Server
-- Prerequisites: Entra admin set on SQL Server, managed identity granted access
-- =============================================================================

-- Workspaces: one row per workspace (= one database)
CREATE TABLE workspaces (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    name            NVARCHAR(100)   NOT NULL UNIQUE,   -- slug: 'board', 'ceo', 'ops'
    display_name    NVARCHAR(255)   NOT NULL,           -- 'Board', 'CEO Office', 'Operations'
    db_name         NVARCHAR(128)   NOT NULL UNIQUE,   -- actual Azure SQL database name
    is_default      BIT             NOT NULL DEFAULT 0, -- exactly one row should be 1 (General)
    is_archived     BIT             NOT NULL DEFAULT 0, -- archived = read-only, no new data
    created_at      DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    created_by      NVARCHAR(255)   NOT NULL,           -- email of creator
    archived_at     DATETIME2       NULL
);

-- Users: one row per person who accesses the system via MCP token
-- Web users (Azure AD) may not have a row here — they resolve via AD groups
-- But if they also use MCP, they need a row for token linkage
CREATE TABLE users (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    email           NVARCHAR(255)   NOT NULL UNIQUE,
    display_name    NVARCHAR(255)   NULL,
    is_org_admin    BIT             NOT NULL DEFAULT 0, -- cross-workspace super-user
    default_workspace_id INT        NULL,               -- FK to workspaces.id
    created_at      DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    created_by      NVARCHAR(255)   NOT NULL,

    CONSTRAINT FK_users_default_workspace
        FOREIGN KEY (default_workspace_id) REFERENCES workspaces(id)
);

-- Workspace memberships: many-to-many between users and workspaces
CREATE TABLE workspace_members (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    user_id         INT             NOT NULL,
    workspace_id    INT             NOT NULL,
    role            NVARCHAR(20)    NOT NULL,           -- 'viewer', 'member', 'chair'
    added_at        DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    added_by        NVARCHAR(255)   NOT NULL,           -- email of who added them

    CONSTRAINT FK_wm_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT FK_wm_workspace FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
    CONSTRAINT UQ_wm_user_workspace UNIQUE (user_id, workspace_id),
    CONSTRAINT CK_wm_role CHECK (role IN ('viewer', 'member', 'chair'))
);

-- Tokens: MCP authentication tokens, linked to users
-- Moved from workspace databases to control database
CREATE TABLE tokens (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    token_hash      NVARCHAR(64)    NOT NULL UNIQUE,   -- SHA256 hex
    user_id         INT             NOT NULL,
    client_name     NVARCHAR(255)   NULL,               -- legacy compat: display name
    is_active       BIT             NOT NULL DEFAULT 1,
    created_at      DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    created_by      NVARCHAR(255)   NOT NULL,
    expires_at      DATETIME2       NULL,               -- NULL = no expiry
    revoked_at      DATETIME2       NULL,
    notes           NVARCHAR(500)   NULL,

    CONSTRAINT FK_tokens_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Audit log: every data access logged
CREATE TABLE audit_log (
    id              BIGINT IDENTITY(1,1) PRIMARY KEY,
    user_email      NVARCHAR(255)   NOT NULL,
    workspace_id    INT             NULL,               -- NULL for cross-workspace ops
    workspace_name  NVARCHAR(100)   NULL,               -- denormalised for query speed
    operation       NVARCHAR(50)    NOT NULL,           -- 'read', 'create', 'update', 'delete'
    entity_type     NVARCHAR(50)    NOT NULL,           -- 'meeting', 'action', 'decision', 'workspace', 'member'
    entity_id       INT             NULL,               -- ID of the entity, NULL for list ops
    detail          NVARCHAR(500)   NULL,               -- optional context
    timestamp       DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    auth_method     NVARCHAR(20)    NOT NULL            -- 'mcp', 'web', 'oauth', 'admin'
);

-- Indexes for common query patterns
CREATE INDEX IX_wm_user_id ON workspace_members(user_id);
CREATE INDEX IX_wm_workspace_id ON workspace_members(workspace_id);
CREATE INDEX IX_tokens_hash ON tokens(token_hash) WHERE is_active = 1;
CREATE INDEX IX_tokens_user ON tokens(user_id);
CREATE INDEX IX_audit_user ON audit_log(user_email, timestamp DESC);
CREATE INDEX IX_audit_workspace ON audit_log(workspace_id, timestamp DESC);
CREATE INDEX IX_audit_timestamp ON audit_log(timestamp DESC);

-- Seed the General workspace (default, created during deployment)
-- db_name will be set by the deploy script based on client name
-- INSERT INTO workspaces (name, display_name, db_name, is_default, created_by)
-- VALUES ('general', 'General', '{client}-mi-general', 1, 'system@generationai.co.nz');
