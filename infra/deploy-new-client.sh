#!/bin/bash
set -euo pipefail

# =============================================================================
# deploy-new-client.sh — Full greenfield client deployment
# =============================================================================
#
# Wraps deploy-bicep.sh with all pre and post steps for a new client
# environment. Handles: app registration config, infra provisioning,
# SQL firewall, database initialisation, token generation, and CORS.
#
# Phase order:
#   Prereqs  — CLI tools, param file, parse config
#   Phase 0  — App Registration (identifier URI, scope, token v2)
#   Phase 1  — Infrastructure (deploy-bicep.sh, health check skipped)
#   Firewall — Temporary SQL firewall rule for deployer IP
#   Phase 2  — Database init (MI user, schema, migrations)
#   Firewall — Auto-removed on exit (trap)
#   Phase 3  — Token generation
#   Phase 4  — CORS origin writeback to param file
#   Phase 5  — Final health check (post-DB-init)
#
# Usage:
#   ./infra/deploy-new-client.sh <environment-name> [image-tag]
#
# Examples:
#   ./infra/deploy-new-client.sh acme-corp
#   ./infra/deploy-new-client.sh acme-corp 20260224120000
#
# Prerequisites:
#   - Azure CLI authenticated (az login)
#   - .env.deploy file with JWT_SECRET
#   - Parameter file at infra/parameters/<env>.bicepparam
#   - App Registration already created (client ID in param file)
#   - sqlcmd installed (for database init) — install: brew install sqlcmd
#   - ODBC Driver 18 for SQL Server installed (for migrate.py)
#   - uv installed (for token generation)
#
# What stays manual:
#   - App Registration creation (requires Azure AD decisions per client)
#   - Creating the .bicepparam file (per-client config)
#   - Admin consent (requires Global Admin)

ENV=${1:?Usage: ./infra/deploy-new-client.sh <environment-name> [image-tag]}
IMAGE_TAG=${2:-$(date +%Y%m%d%H%M%S)}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_NAME="mi-${ENV}"
RESOURCE_GROUP="meeting-intelligence-${ENV}-rg"
SQL_SERVER="mi-${ENV}-sql.database.windows.net"
SQL_SERVER_NAME="mi-${ENV}-sql"
SQL_DATABASE="mi-${ENV}"
CONTROL_DATABASE="mi-${ENV}-control"

echo "=== New Client Deployment: ${ENV} ==="
echo ""

# =========================================================================
# PREREQUISITE CHECKS
# =========================================================================
echo "--- Checking prerequisites ---"
PREREQ_OK=true

if ! command -v az &>/dev/null; then
    echo "  MISSING: az (Azure CLI)"
    PREREQ_OK=false
else
    echo "  OK: az"
fi

if ! command -v uv &>/dev/null; then
    echo "  MISSING: uv (required for token generation)"
    PREREQ_OK=false
else
    echo "  OK: uv"
fi

HAS_SQLCMD=false
if command -v sqlcmd &>/dev/null; then
    echo "  OK: sqlcmd"
    HAS_SQLCMD=true
else
    echo "  MISSING: sqlcmd (database init will use Python fallback)"
    echo "           Install: brew install sqlcmd"
fi

PARAM_FILE="${SCRIPT_DIR}/parameters/${ENV}.bicepparam"
if [ ! -f "$PARAM_FILE" ]; then
    echo "  MISSING: Parameter file at ${PARAM_FILE}"
    echo "           Create one based on an existing .bicepparam before deploying."
    PREREQ_OK=false
else
    echo "  OK: ${PARAM_FILE}"
fi

if [ "$PREREQ_OK" = false ]; then
    echo ""
    echo "ERROR: Prerequisites not met. Fix the issues above and retry."
    exit 1
fi

# Parse config from parameter file
CLIENT_ID=$(grep "param azureClientId" "$PARAM_FILE" | sed "s/.*= '//;s/'.*//")
ALLOWED_USERS=$(grep "param allowedUsers" "$PARAM_FILE" | sed "s/.*= '//;s/'.*//")
# First email in allowedUsers is the primary client contact
PRIMARY_EMAIL=$(echo "$ALLOWED_USERS" | cut -d',' -f1 | xargs)

# =========================================================================
# SQL FIREWALL: Cleanup trap for temporary deployer IP rule
# =========================================================================
FW_RULE_NAME="deploy-temp-${ENV}"
FW_RULE_CREATED=false

cleanup_firewall() {
    if [ "$FW_RULE_CREATED" = true ]; then
        echo ""
        echo "--- Cleaning up temporary SQL firewall rule ---"
        cd "$REPO_ROOT" 2>/dev/null || true
        local output
        if output=$(az sql server firewall-rule delete \
            --server "$SQL_SERVER_NAME" -g "$RESOURCE_GROUP" \
            --name "$FW_RULE_NAME" 2>&1); then
            echo "Firewall rule '${FW_RULE_NAME}': removed"
        else
            echo "ERROR: Failed to remove firewall rule '${FW_RULE_NAME}'"
            echo "  Output: ${output}"
            echo "  Manual cleanup: az sql server firewall-rule delete --server $SQL_SERVER_NAME -g $RESOURCE_GROUP --name $FW_RULE_NAME"
        fi
    fi
}
trap cleanup_firewall EXIT

echo ""

# =========================================================================
# PHASE 0: App Registration configuration
# =========================================================================
# Automates 3 configs that were previously manual post-deploy steps:
#   1. Identifier URI (api://<clientId>)
#   2. access_as_user OAuth scope
#   3. requestedAccessTokenVersion=2 (v2 tokens)
# SPA redirect URIs (#4) are handled by deploy-bicep.sh Phase 9.
echo "=========================================="
echo "PHASE 0: App Registration configuration"
echo "=========================================="
echo ""

APP_REG_OK=true

# Get the Object ID (Graph API needs this, not the Client/Application ID)
OBJECT_ID=$(az ad app show --id "$CLIENT_ID" --query id -o tsv 2>/dev/null || echo "")
if [ -z "$OBJECT_ID" ]; then
    echo "WARNING: Could not find App Registration for client ID: ${CLIENT_ID}"
    echo "Skipping App Registration configuration. Configure manually."
    APP_REG_OK=false
else
    echo "App Registration found: ${CLIENT_ID} (object: ${OBJECT_ID})"

    # --- Step 0a: Identifier URI ---
    echo ""
    echo "--- Setting Identifier URI ---"
    EXISTING_URI=$(az ad app show --id "$CLIENT_ID" --query "identifierUris[0]" -o tsv 2>/dev/null || echo "")
    if [ "$EXISTING_URI" = "api://${CLIENT_ID}" ]; then
        echo "Identifier URI: already set"
    else
        if az ad app update --id "$CLIENT_ID" --identifier-uris "api://${CLIENT_ID}" 2>/dev/null; then
            echo "Identifier URI: set to api://${CLIENT_ID}"
        else
            echo "WARNING: Could not set Identifier URI (may require higher permissions)"
            APP_REG_OK=false
        fi
    fi

    # --- Step 0b: access_as_user scope + requestedAccessTokenVersion=2 ---
    echo ""
    echo "--- Configuring API scope and token version ---"

    # Check if scope already exists — reuse its UUID if so
    EXISTING_SCOPE_ID=$(az ad app show --id "$CLIENT_ID" \
        --query "api.oauth2PermissionScopes[?value=='access_as_user'].id | [0]" -o tsv 2>/dev/null || echo "")

    if [ -n "$EXISTING_SCOPE_ID" ] && [ "$EXISTING_SCOPE_ID" != "None" ]; then
        echo "access_as_user scope: already exists (${EXISTING_SCOPE_ID})"
        SCOPE_ID="$EXISTING_SCOPE_ID"
    else
        # Deterministic UUID from CLIENT_ID — same on re-runs
        SCOPE_ID=$(python3 -c "import uuid; print(uuid.uuid5(uuid.NAMESPACE_URL, '${CLIENT_ID}/access_as_user'))")
    fi

    # Check current token version
    CURRENT_TOKEN_VERSION=$(az ad app show --id "$CLIENT_ID" \
        --query "api.requestedAccessTokenVersion" -o tsv 2>/dev/null || echo "")

    NEEDS_SCOPE=false
    NEEDS_VERSION=false
    if [ -z "$EXISTING_SCOPE_ID" ] || [ "$EXISTING_SCOPE_ID" = "None" ]; then
        NEEDS_SCOPE=true
    fi
    if [ "$CURRENT_TOKEN_VERSION" != "2" ]; then
        NEEDS_VERSION=true
    fi

    if [ "$NEEDS_SCOPE" = true ] || [ "$NEEDS_VERSION" = true ]; then
        # Build Graph API PATCH body — single call to avoid overwriting fields
        if [ "$NEEDS_SCOPE" = true ]; then
            API_BODY=$(cat <<EOFBODY
{"api":{"requestedAccessTokenVersion":2,"oauth2PermissionScopes":[{"id":"${SCOPE_ID}","adminConsentDisplayName":"Access Meeting Intelligence as user","adminConsentDescription":"Allow the application to access Meeting Intelligence on behalf of the signed-in user.","userConsentDisplayName":"Access Meeting Intelligence as you","userConsentDescription":"Allow the application to access Meeting Intelligence on your behalf.","isEnabled":true,"type":"User","value":"access_as_user"}]}}
EOFBODY
)
        else
            # Only token version needs update — omit scopes to preserve existing
            API_BODY='{"api":{"requestedAccessTokenVersion":2}}'
        fi

        if az rest --method PATCH \
            --url "https://graph.microsoft.com/v1.0/applications/${OBJECT_ID}" \
            --headers "Content-Type=application/json" \
            --body "$API_BODY" 2>/dev/null; then
            [ "$NEEDS_SCOPE" = true ] && echo "access_as_user scope: created (${SCOPE_ID})"
            [ "$NEEDS_VERSION" = true ] && echo "Token version: set to v2"
        else
            echo "WARNING: Could not configure API scope/token version via Graph API"
            echo "This may require Application.ReadWrite.All permission."
            echo ""
            echo "Manual steps:"
            if [ "$NEEDS_SCOPE" = true ]; then
                echo "  1. Azure Portal > App Registrations > ${CLIENT_ID} > Expose an API > Add scope 'access_as_user'"
            fi
            if [ "$NEEDS_VERSION" = true ]; then
                echo "  2. App Registration manifest > set accessTokenAcceptedVersion to 2"
            fi
            APP_REG_OK=false
        fi
    else
        echo "API scope and token version: already configured"
    fi
fi

if [ "$APP_REG_OK" = true ]; then
    echo ""
    echo "App Registration: fully configured"
else
    echo ""
    echo "App Registration: some steps need manual attention (see above)"
fi
echo ""

# =========================================================================
# PHASE 1: Infrastructure (deploy-bicep.sh)
# =========================================================================
echo "=========================================="
echo "PHASE 1: Infrastructure provisioning"
echo "=========================================="
echo ""

SKIP_HEALTH_CHECK=1 "${SCRIPT_DIR}/deploy-bicep.sh" "$ENV" "$IMAGE_TAG"

# Capture FQDN from the deployed container app
FQDN=$(az containerapp show -n "$APP_NAME" -g "$RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv)
echo ""

# =========================================================================
# SQL FIREWALL: Add temporary deployer IP rule
# =========================================================================
echo "--- Adding temporary SQL firewall rule for deployer IP ---"
DEPLOYER_IP=$(curl -s --max-time 10 ifconfig.me)
if [ -z "$DEPLOYER_IP" ]; then
    echo "WARNING: Could not detect deployer IP. DB init may fail if SQL firewall blocks access."
    echo "Add manually: az sql server firewall-rule create --server $SQL_SERVER_NAME -g $RESOURCE_GROUP --name $FW_RULE_NAME --start-ip-address <YOUR-IP> --end-ip-address <YOUR-IP>"
else
    echo "Deployer IP: ${DEPLOYER_IP}"
    if az sql server firewall-rule create \
        --server "$SQL_SERVER_NAME" -g "$RESOURCE_GROUP" \
        --name "$FW_RULE_NAME" \
        --start-ip-address "$DEPLOYER_IP" \
        --end-ip-address "$DEPLOYER_IP" \
        --output none 2>&1; then
        FW_RULE_CREATED=true
        echo "Firewall rule '${FW_RULE_NAME}': created (will auto-remove on exit)"
    else
        echo "WARNING: Could not create firewall rule. DB init may fail."
        echo "Possible cause: insufficient permissions on SQL server resource"
    fi
fi
echo ""

# =========================================================================
# PHASE 2: Database initialisation (control DB + general workspace DB)
# =========================================================================
echo "=========================================="
echo "PHASE 2: Database initialisation"
echo "=========================================="
echo ""
echo "Control DB:   ${CONTROL_DATABASE}"
echo "General DB:   ${SQL_DATABASE}"
echo ""

DB_INIT_OK=true

# Load the grant-mi-access.sql template
GRANT_MI_TEMPLATE="${REPO_ROOT}/scripts/grant-mi-access.sql"
if [ ! -f "$GRANT_MI_TEMPLATE" ]; then
    echo "WARNING: grant-mi-access.sql not found at ${GRANT_MI_TEMPLATE}"
    echo "Using inline SQL for MI user creation"
fi

# Helper: run SQL against a database (sqlcmd preferred, Python fallback)
run_sql_against_db() {
    local target_db="$1"
    local sql_text="$2"
    local label="$3"

    if [ "$HAS_SQLCMD" = true ]; then
        if sqlcmd -S "$SQL_SERVER" -d "$target_db" -G --authentication-method=ActiveDirectoryDefault \
            -Q "$sql_text" 2>&1; then
            echo "  ${label}: OK"
            return 0
        else
            echo "  WARNING: ${label} failed via sqlcmd"
            return 1
        fi
    else
        if python3 -c "
import struct, sys
try:
    from azure.identity import DefaultAzureCredential
    import pyodbc, re
    credential = DefaultAzureCredential()
    token_bytes = credential.get_token('https://database.windows.net/.default').token.encode('UTF-16-LE')
    token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)
    conn_str = 'DRIVER={ODBC Driver 18 for SQL Server};SERVER=${SQL_SERVER};DATABASE=${target_db};Encrypt=yes;TrustServerCertificate=no;'
    conn = pyodbc.connect(conn_str, attrs_before={1256: token_struct})
    cursor = conn.cursor()
    sql = '''${sql_text}'''
    for batch in re.split(r'^\s*GO\s*$', sql, flags=re.MULTILINE | re.IGNORECASE):
        batch = batch.strip()
        if batch:
            cursor.execute(batch)
    conn.commit()
    conn.close()
    print('  ${label}: OK')
except Exception as e:
    print(f'  ERROR: {e}')
    sys.exit(1)
" 2>&1; then
            return 0
        else
            echo "  WARNING: ${label} failed via Python fallback"
            return 1
        fi
    fi
}

# Helper: run SQL file against a database
run_sql_file_against_db() {
    local target_db="$1"
    local sql_file="$2"
    local label="$3"

    if [ "$HAS_SQLCMD" = true ]; then
        if sqlcmd -S "$SQL_SERVER" -d "$target_db" -G --authentication-method=ActiveDirectoryDefault \
            -i "$sql_file" 2>&1; then
            echo "  ${label}: OK"
            return 0
        else
            echo "  WARNING: ${label} failed via sqlcmd"
            return 1
        fi
    else
        if python3 -c "
import struct, sys, re
try:
    from azure.identity import DefaultAzureCredential
    import pyodbc
    credential = DefaultAzureCredential()
    token_bytes = credential.get_token('https://database.windows.net/.default').token.encode('UTF-16-LE')
    token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)
    conn_str = 'DRIVER={ODBC Driver 18 for SQL Server};SERVER=${SQL_SERVER};DATABASE=${target_db};Encrypt=yes;TrustServerCertificate=no;'
    conn = pyodbc.connect(conn_str, attrs_before={1256: token_struct})
    cursor = conn.cursor()
    sql = open('${sql_file}').read()
    for batch in re.split(r'^\s*GO\s*\$', sql, flags=re.MULTILINE | re.IGNORECASE):
        batch = batch.strip()
        if batch:
            cursor.execute(batch)
    conn.commit()
    conn.close()
    print('  ${label}: OK')
except Exception as e:
    print(f'  ERROR: {e}')
    sys.exit(1)
" 2>&1; then
            return 0
        else
            echo "  WARNING: ${label} failed via Python fallback"
            return 1
        fi
    fi
}

# Step 2a: Grant MI access to BOTH databases
echo "--- Step 2a: Grant managed identity access ---"
MI_USER_SQL="IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = '${APP_NAME}')
BEGIN
    CREATE USER [${APP_NAME}] FROM EXTERNAL PROVIDER;
    ALTER ROLE db_datareader ADD MEMBER [${APP_NAME}];
    ALTER ROLE db_datawriter ADD MEMBER [${APP_NAME}];
    PRINT 'User created and roles assigned';
END
ELSE
    PRINT 'User already exists -- skipping';"

echo "Granting MI access to control database (${CONTROL_DATABASE})..."
if ! run_sql_against_db "$CONTROL_DATABASE" "$MI_USER_SQL" "MI user on control DB"; then
    DB_INIT_OK=false
fi

echo "Granting MI access to general workspace database (${SQL_DATABASE})..."
if ! run_sql_against_db "$SQL_DATABASE" "$MI_USER_SQL" "MI user on general DB"; then
    DB_INIT_OK=false
fi

# Grant dbmanager on master so the admin API can create workspace databases at runtime
echo "Granting MI dbmanager role on master (for workspace creation)..."
MI_DBMANAGER_SQL="IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = '${APP_NAME}')
    CREATE USER [${APP_NAME}] FROM EXTERNAL PROVIDER;
ALTER ROLE dbmanager ADD MEMBER [${APP_NAME}];
PRINT 'dbmanager granted on master';"

if ! run_sql_against_db "master" "$MI_DBMANAGER_SQL" "MI dbmanager on master"; then
    echo "  WARNING: dbmanager grant failed (workspace creation via admin API will not work)"
fi
echo ""

# Step 2b: Apply control schema
echo "--- Step 2b: Apply control database schema ---"
CONTROL_SCHEMA_FILE="${REPO_ROOT}/scripts/control_schema.sql"
if [ ! -f "$CONTROL_SCHEMA_FILE" ]; then
    echo "  ERROR: Control schema file not found: ${CONTROL_SCHEMA_FILE}"
    DB_INIT_OK=false
else
    # Check if already applied
    CONTROL_TABLE_CHECK="0"
    if [ "$HAS_SQLCMD" = true ]; then
        CONTROL_TABLE_CHECK=$(sqlcmd -S "$SQL_SERVER" -d "$CONTROL_DATABASE" -G --authentication-method=ActiveDirectoryDefault \
            -Q "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'workspaces'" -h -1 2>/dev/null | xargs || echo "0")
    fi
    if [ "$CONTROL_TABLE_CHECK" -gt 0 ] 2>/dev/null; then
        echo "  Control schema already applied -- skipping"
    else
        if ! run_sql_file_against_db "$CONTROL_DATABASE" "$CONTROL_SCHEMA_FILE" "Control schema"; then
            DB_INIT_OK=false
        fi
    fi
fi
echo ""

# Step 2c: Apply workspace schema (schema.sql) to general database
echo "--- Step 2c: Apply workspace database schema ---"
WORKSPACE_SCHEMA_FILE="${REPO_ROOT}/schema.sql"
# Check if already applied
WS_TABLE_CHECK="0"
if [ "$HAS_SQLCMD" = true ]; then
    WS_TABLE_CHECK=$(sqlcmd -S "$SQL_SERVER" -d "$SQL_DATABASE" -G --authentication-method=ActiveDirectoryDefault \
        -Q "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'Meeting'" -h -1 2>/dev/null | xargs || echo "0")
fi
if [ "$WS_TABLE_CHECK" -gt 0 ] 2>/dev/null; then
    echo "  Workspace schema already applied -- skipping"
else
    if ! run_sql_file_against_db "$SQL_DATABASE" "$WORKSPACE_SCHEMA_FILE" "Workspace schema"; then
        DB_INIT_OK=false
    fi
fi
echo ""

# Step 2d: Run migrations on general workspace database
echo "--- Step 2d: Run workspace database migrations ---"
if cd "${REPO_ROOT}/server" && uv run python -m scripts.migrate \
    --server "$SQL_SERVER" --database "$SQL_DATABASE" 2>&1; then
    echo "  Migrations: OK"
else
    echo "  WARNING: Migration runner failed"
    echo "  Run manually: cd server && uv run python -m scripts.migrate --server $SQL_SERVER --database $SQL_DATABASE"
    DB_INIT_OK=false
fi
cd "$REPO_ROOT"
echo ""

# Step 2e: Seed General workspace in control database
echo "--- Step 2e: Seed General workspace ---"
SEED_SQL="IF NOT EXISTS (SELECT 1 FROM workspaces WHERE name = 'general')
BEGIN
    INSERT INTO workspaces (name, display_name, db_name, is_default, created_by)
    VALUES ('general', 'General', '${SQL_DATABASE}', 1, 'system@generationai.co.nz');
    PRINT 'General workspace seeded';
END
ELSE
    PRINT 'General workspace already exists -- skipping';"

if ! run_sql_against_db "$CONTROL_DATABASE" "$SEED_SQL" "Seed General workspace"; then
    DB_INIT_OK=false
fi
echo ""

if [ "$DB_INIT_OK" = false ]; then
    echo "WARNING: Some database steps failed. Manual intervention may be needed."
    echo "See instructions in the summary below."
    echo ""
fi

# =========================================================================
# PHASE 3: Token generation
# =========================================================================
echo "=========================================="
echo "PHASE 3: Token generation"
echo "=========================================="
echo ""

TOKEN_OK=true
if [ "$DB_INIT_OK" = true ]; then
    echo "Creating client token for ${ENV}..."
    # Set DB env vars for manage_tokens.py (reads AZURE_SQL_SERVER + CONTROL_DB_NAME)
    export AZURE_SQL_SERVER="$SQL_SERVER"
    export AZURE_SQL_DATABASE="$SQL_DATABASE"
    export CONTROL_DB_NAME="$CONTROL_DATABASE"

    TOKEN_OUTPUT=$(cd "${REPO_ROOT}/server" && uv run python scripts/manage_tokens.py create \
        --user "$PRIMARY_EMAIL" \
        --workspace "general" \
        --role "chair" \
        --notes "Auto-generated by deploy-new-client.sh" 2>&1) || TOKEN_OK=false

    if [ "$TOKEN_OK" = true ]; then
        echo "$TOKEN_OUTPUT"
    else
        echo "WARNING: Token creation failed"
        echo "$TOKEN_OUTPUT"
        echo ""
        echo "Create manually:"
        echo "  cd server && AZURE_SQL_SERVER=$SQL_SERVER CONTROL_DB_NAME=$CONTROL_DATABASE \\"
        echo "    uv run python scripts/manage_tokens.py create --user '$PRIMARY_EMAIL' --workspace general --role chair"
    fi
else
    echo "SKIPPED: Database init had failures — token creation requires working DB"
    echo ""
    echo "Create manually after fixing DB:"
    echo "  cd server && AZURE_SQL_SERVER=$SQL_SERVER CONTROL_DB_NAME=$CONTROL_DATABASE \\"
    echo "    uv run python scripts/manage_tokens.py create --user '$PRIMARY_EMAIL' --workspace general --role chair"
    TOKEN_OK=false
fi
echo ""

# =========================================================================
# PHASE 4: CORS origin writeback to param file
# =========================================================================
echo "=========================================="
echo "PHASE 4: CORS origin writeback"
echo "=========================================="
echo ""

CURRENT_CORS=$(grep "param corsOrigins" "$PARAM_FILE" | sed "s/.*= '//;s/'.*//")
EXPECTED_CORS="https://${FQDN}"

if [ "$CURRENT_CORS" = "$EXPECTED_CORS" ]; then
    echo "Param file already has correct CORS origin — no change needed"
else
    echo "Updating ${PARAM_FILE}..."
    echo "  Old: ${CURRENT_CORS}"
    echo "  New: ${EXPECTED_CORS}"
    # Use | as sed delimiter since URLs contain /
    sed -i '' "s|param corsOrigins = '.*'|param corsOrigins = '${EXPECTED_CORS}'|" "$PARAM_FILE"
    echo "CORS origin updated in param file"
    echo ""
    echo "NOTE: This modified a git-tracked file. Commit the change:"
    echo "  git add ${PARAM_FILE}"
    echo "  git commit -m 'chore: set CORS origin for ${ENV}'"
fi
echo ""

# =========================================================================
# PHASE 5: Final health check
# =========================================================================
echo "=========================================="
echo "PHASE 5: Final health check"
echo "=========================================="
echo ""

echo "URL: https://${FQDN}/health/ready"
RETRIES=0
MAX_RETRIES=6
HEALTHY=false
while [ $RETRIES -lt $MAX_RETRIES ]; do
    if curl -sf "https://${FQDN}/health/ready" > /dev/null 2>&1; then
        echo "Health: READY"
        HEALTHY=true
        break
    fi
    RETRIES=$((RETRIES + 1))
    echo "Waiting... (${RETRIES}/${MAX_RETRIES})"
    sleep 10
done

if [ "$HEALTHY" = false ]; then
    echo "WARNING: Health check did not pass"
    echo "Check: az containerapp logs show -n $APP_NAME -g $RESOURCE_GROUP --type system"
fi
echo ""

# =========================================================================
# SUMMARY
# =========================================================================
echo "=========================================="
echo "DEPLOYMENT SUMMARY"
echo "=========================================="
echo ""
echo "Environment:  ${ENV}"
echo "Container:    ${APP_NAME}"
echo "SQL Server:   ${SQL_SERVER_NAME}"
echo "Control DB:   ${CONTROL_DATABASE}"
echo "General DB:   ${SQL_DATABASE}"
echo "URL:          https://${FQDN}"
echo "Health:       https://${FQDN}/health/ready"
echo "MCP (SSE):    https://${FQDN}/sse?token=<TOKEN>"
echo "MCP (HTTP):   https://${FQDN}/mcp"
echo "Web UI:       https://${FQDN}"
echo ""

# Report what succeeded and what needs manual attention
echo "--- Status ---"
echo "Infrastructure:  OK (deploy-bicep.sh completed)"
if [ "$DB_INIT_OK" = true ]; then
    echo "Database:        OK"
else
    echo "Database:        NEEDS ATTENTION (see below)"
fi
if [ "$TOKEN_OK" = true ]; then
    echo "Token:           OK"
else
    echo "Token:           NEEDS ATTENTION (see below)"
fi
if [ "$HEALTHY" = true ]; then
    echo "Health:          OK"
else
    echo "Health:          NEEDS ATTENTION"
fi
echo ""

# Print manual steps only for what failed or can't be automated
HAS_MANUAL_STEPS=false

if [ "$DB_INIT_OK" = false ]; then
    HAS_MANUAL_STEPS=true
    echo "--- Database manual steps ---"
    echo ""
    echo "1. Grant MI access to both databases (run against each):"
    echo "   sqlcmd -S $SQL_SERVER -d $CONTROL_DATABASE -G --authentication-method=ActiveDirectoryDefault"
    echo "   sqlcmd -S $SQL_SERVER -d $SQL_DATABASE -G --authentication-method=ActiveDirectoryDefault"
    echo "   > CREATE USER [${APP_NAME}] FROM EXTERNAL PROVIDER;"
    echo "   > ALTER ROLE db_datareader ADD MEMBER [${APP_NAME}];"
    echo "   > ALTER ROLE db_datawriter ADD MEMBER [${APP_NAME}];"
    echo ""
    echo "2. Apply control schema:"
    echo "   sqlcmd -S $SQL_SERVER -d $CONTROL_DATABASE -G --authentication-method=ActiveDirectoryDefault -i scripts/control_schema.sql"
    echo ""
    echo "3. Apply workspace schema:"
    echo "   sqlcmd -S $SQL_SERVER -d $SQL_DATABASE -G --authentication-method=ActiveDirectoryDefault -i schema.sql"
    echo ""
    echo "4. Run migrations on workspace DB:"
    echo "   cd server && uv run python -m scripts.migrate --server $SQL_SERVER --database $SQL_DATABASE"
    echo ""
    echo "5. Seed General workspace:"
    echo "   sqlcmd -S $SQL_SERVER -d $CONTROL_DATABASE -G --authentication-method=ActiveDirectoryDefault"
    echo "   > INSERT INTO workspaces (name, display_name, db_name, is_default, created_by)"
    echo "     VALUES ('general', 'General', '$SQL_DATABASE', 1, 'system@generationai.co.nz');"
    echo ""
fi

if [ "$TOKEN_OK" = false ]; then
    HAS_MANUAL_STEPS=true
    echo "--- Token manual step ---"
    echo ""
    echo "Create token:"
    echo "  cd server && AZURE_SQL_SERVER=$SQL_SERVER CONTROL_DB_NAME=$CONTROL_DATABASE \\"
    echo "    uv run python scripts/manage_tokens.py create --user '$PRIMARY_EMAIL' --workspace general --role chair"
    echo ""
fi

# Admin consent is always manual
HAS_MANUAL_STEPS=true
echo "--- Always manual ---"
echo ""
echo "Grant admin consent (requires Global Admin):"
echo "  Azure Portal > App Registrations > ${CLIENT_ID} > API Permissions > Grant admin consent"
echo ""

if [ "$HAS_MANUAL_STEPS" = true ]; then
    echo "Complete the manual steps above, then verify:"
    echo "  curl -sf https://${FQDN}/health/ready && echo OK"
fi
