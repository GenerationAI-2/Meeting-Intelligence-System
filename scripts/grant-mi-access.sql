-- =============================================================================
-- Grant Managed Identity Access to Database
-- =============================================================================
-- Run against each database the container app needs access to.
-- Replace {APP_NAME} with the container app name (e.g., mi-marshall).
--
-- Prerequisites:
--   - Entra admin set on the SQL Server
--   - SQL Server identity has User.Read.All Graph permission
--     (required for FROM EXTERNAL PROVIDER)
--
-- If Craig overrides to SID-based: replace FROM EXTERNAL PROVIDER with
--   WITH SID = <computed-sid>, TYPE = E
--   where SID = CAST(CAST('<client-id>' AS UNIQUEIDENTIFIER) AS VARBINARY(16))
-- =============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = '{APP_NAME}')
BEGIN
    CREATE USER [{APP_NAME}] FROM EXTERNAL PROVIDER;
    ALTER ROLE db_datareader ADD MEMBER [{APP_NAME}];
    ALTER ROLE db_datawriter ADD MEMBER [{APP_NAME}];
    PRINT 'User [{APP_NAME}] created and roles assigned';
END
ELSE
    PRINT 'User [{APP_NAME}] already exists -- skipping';
