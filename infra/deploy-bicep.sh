#!/bin/bash
set -euo pipefail

# =============================================================================
# deploy-bicep.sh — Deploy Meeting Intelligence via Bicep IaC
# =============================================================================
#
# Greenfield environments:  Full end-to-end provisioning (two-phase Bicep deploy
#   with automated AcrPull, Key Vault RBAC, CORS, SPA redirect URIs, health check)
# Existing Bicep environments:  Image + infra update via single Bicep deploy
# All environments are Bicep-managed (team/demo decommissioned Feb 2026)
#
# Usage:
#   ./infra/deploy-bicep.sh <environment-name> [image-tag]
#
# Examples:
#   ./infra/deploy-bicep.sh marshall 20260224120000
#   ./infra/deploy-bicep.sh new-client                # auto-generates timestamp tag
#
# Prerequisites:
#   - Azure CLI authenticated (az login)
#   - Parameter file at infra/parameters/<env>.bicepparam

ENV=${1:?Usage: ./infra/deploy-bicep.sh <environment-name> [image-tag]}
IMAGE_TAG=${2:-$(date +%Y%m%d%H%M%S)}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ACR_NAME="meetingintelacr20260116"

# --- Detect CAF naming from parameter file ---
PARAM_FILE_CHECK="${SCRIPT_DIR}/parameters/${ENV}.bicepparam"
CAF_NAMING=$(grep "param cafNaming" "$PARAM_FILE_CHECK" 2>/dev/null | grep -c "true" || echo "0")
ENV_TYPE=$(grep "param environmentType" "$PARAM_FILE_CHECK" 2>/dev/null | sed "s/.*= '//;s/'.*//" || echo "prod")
LOCATION=$(grep "param location" "$PARAM_FILE_CHECK" 2>/dev/null | sed "s/.*= '//;s/'.*//" || echo "australiaeast")

if [ "$CAF_NAMING" -gt 0 ]; then
    APP_NAME="ca-mi-${ENV_TYPE}-${ENV}"
    RESOURCE_GROUP="rg-app-${ENV_TYPE}-mi-${ENV}"
    KV_NAME="kv-mi-${ENV_TYPE}-${ENV}"
    echo "Naming: CAF (${ENV_TYPE})"
else
    APP_NAME="mi-${ENV}"
    RESOURCE_GROUP="meeting-intelligence-${ENV}-rg"
    KV_NAME="mi-${ENV}-kv"
    echo "Naming: Legacy"
fi

# --- Set subscription if specified ---
PARAM_SUBSCRIPTION=$(grep "param subscriptionId" "$PARAM_FILE_CHECK" 2>/dev/null | sed "s/.*= '//;s/'.*//" || echo "")
TARGET_SUBSCRIPTION="${AZURE_SUBSCRIPTION_ID:-$PARAM_SUBSCRIPTION}"
if [ -n "$TARGET_SUBSCRIPTION" ]; then
    echo "Setting subscription: ${TARGET_SUBSCRIPTION}"
    az account set --subscription "$TARGET_SUBSCRIPTION"
fi

# All environments are Bicep-managed (team/demo decommissioned Feb 2026)

echo "=== Deploying Meeting Intelligence: ${ENV} ==="
echo "Resource Group: ${RESOURCE_GROUP}"
echo "Image Tag: ${IMAGE_TAG}"
echo ""

# --- Load secrets from .env.deploy ---
if [ -f "${REPO_ROOT}/.env.deploy" ]; then
    echo "Loading secrets from .env.deploy..."
    set -a
    source "${REPO_ROOT}/.env.deploy"
    set +a
fi

# --- Validate parameter file ---
PARAM_FILE="${SCRIPT_DIR}/parameters/${ENV}.bicepparam"
if [ ! -f "$PARAM_FILE" ]; then
    echo "ERROR: No parameter file at ${PARAM_FILE}"
    echo "Create one based on an existing .bicepparam file before deploying."
    exit 1
fi

# Parse config from parameter file
CLIENT_ID=$(grep "param azureClientId" "$PARAM_FILE" | sed "s/.*= '//;s/'.*//")
TENANT_ID=$(grep "param azureTenantId" "$PARAM_FILE" | sed "s/.*= '//;s/'.*//")

# Export env vars for readEnvironmentVariable() in .bicepparam files
export CONTAINER_IMAGE_TAG="$IMAGE_TAG"
export APPLICATIONINSIGHTS_CONNECTION_STRING="${APPLICATIONINSIGHTS_CONNECTION_STRING:-}"

# --- Resolve ACR subscription (may differ from target subscription) ---
ACR_SUB=""
if az acr show --name "$ACR_NAME" --query id -o tsv &>/dev/null; then
    ACR_SUB=$(az account show --query id -o tsv)
else
    echo "ACR '${ACR_NAME}' not in current subscription — searching others..."
    for sub in $(az account list --query "[].id" -o tsv); do
        if az acr show --name "$ACR_NAME" --subscription "$sub" --query id -o tsv &>/dev/null; then
            ACR_SUB="$sub"
            echo "ACR found in subscription: $(az account list --query "[?id=='$sub'].name | [0]" -o tsv)"
            break
        fi
    done
fi
if [ -z "$ACR_SUB" ]; then
    echo "ERROR: ACR '${ACR_NAME}' not found in any accessible subscription."
    echo "Check: az acr list --query '[].name' --output table"
    exit 1
fi

# --- Detect greenfield vs existing ---
GREENFIELD=false
if ! az containerapp show -n "$APP_NAME" -g "$RESOURCE_GROUP" &>/dev/null; then
    GREENFIELD=true
    echo "Mode: GREENFIELD (full provisioning sequence)"
else
    echo "Mode: UPDATE (existing environment)"
fi
echo ""

# =========================================================================
# PHASE 1: Build container image
# =========================================================================
echo "--- Phase 1: Building container image ---"
if ! az acr build \
    --registry "$ACR_NAME" \
    --subscription "$ACR_SUB" \
    --image "${APP_NAME}:${IMAGE_TAG}" \
    --file "${REPO_ROOT}/server/Dockerfile" \
    --build-arg VITE_SPA_CLIENT_ID="$CLIENT_ID" \
    --build-arg VITE_API_CLIENT_ID="$CLIENT_ID" \
    --build-arg VITE_AZURE_TENANT_ID="$TENANT_ID" \
    --build-arg VITE_API_URL="/api" \
    "${REPO_ROOT}" \
    --no-logs 2>&1 | tail -20; then
    echo ""
    echo "ERROR: ACR build failed."
    echo "Common causes:"
    echo "  - Dockerfile syntax error or missing dependency"
    echo "  - ACR authentication expired (run: az acr login --name $ACR_NAME)"
    echo "  - Network connectivity to ACR"
    echo ""
    echo "To retry the build manually:"
    echo "  az acr build --registry $ACR_NAME --image ${APP_NAME}:${IMAGE_TAG} \\"
    echo "    --file ${REPO_ROOT}/server/Dockerfile \\"
    echo "    --build-arg VITE_SPA_CLIENT_ID=$CLIENT_ID \\"
    echo "    --build-arg VITE_API_CLIENT_ID=$CLIENT_ID \\"
    echo "    --build-arg VITE_AZURE_TENANT_ID=$TENANT_ID \\"
    echo "    --build-arg VITE_API_URL=/api ${REPO_ROOT}"
    exit 1
fi
echo "Image pushed: ${ACR_NAME}.azurecr.io/${APP_NAME}:${IMAGE_TAG}"
echo ""

# =========================================================================
# PHASE 2: Create resource group
# =========================================================================
echo "--- Phase 2: Creating resource group ---"
az group create \
    --name "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --tags environment="$ENV" project=meeting-intelligence owner=caleb.lucas@generationai.co.nz created-by=bicep \
    --output none
echo ""

# =========================================================================
# PHASE 3: Bicep deploy
# =========================================================================
echo "--- Phase 3: Deploying Bicep templates ---"
BICEP_OK=true
if ! az deployment group create \
    --resource-group "$RESOURCE_GROUP" \
    --template-file "${SCRIPT_DIR}/main.bicep" \
    --parameters "$PARAM_FILE" \
    --output none 2>&1; then
    BICEP_OK=false
    if [ "$GREENFIELD" = true ]; then
        echo "Bicep deploy had failures (expected on greenfield — AcrPull not yet assigned)"
    else
        echo "WARNING: Bicep deploy had failures on existing environment"
        echo "Continuing to verify container app is functional..."
    fi
fi
echo ""

# =========================================================================
# PHASE 4: AcrPull role assignment (idempotent)
# =========================================================================
# container-app.bicep uses identity:'system' for ACR registry config, but this
# does NOT create an AcrPull role assignment. The ACR is in a different resource
# group (meeting-intelligence-v2-rg), making cross-RG Bicep role assignment
# complex. Handled here in the deploy script instead.
echo "--- Phase 4: Ensuring AcrPull role assignment ---"
PRINCIPAL_ID=$(az containerapp show -n "$APP_NAME" -g "$RESOURCE_GROUP" --query "identity.principalId" -o tsv 2>/dev/null || echo "")
if [ -z "$PRINCIPAL_ID" ]; then
    echo "ERROR: Container App '${APP_NAME}' not found or has no managed identity."
    echo "The Bicep deploy may have failed before creating the Container App."
    echo "Check: az deployment group show -g $RESOURCE_GROUP -n main --query properties.error"
    exit 1
fi

ACR_ID=$(az acr show --name "$ACR_NAME" --subscription "$ACR_SUB" --query id -o tsv)
EXISTING_ACR_ROLE=$(az role assignment list --assignee "$PRINCIPAL_ID" --role AcrPull --scope "$ACR_ID" --query "length(@)" -o tsv 2>/dev/null || echo "0")
if [ "${EXISTING_ACR_ROLE:-0}" -gt 0 ] 2>/dev/null; then
    echo "AcrPull: already assigned"
else
    az role assignment create --assignee "$PRINCIPAL_ID" --role AcrPull --scope "$ACR_ID" --output none
    echo "AcrPull: assigned"
fi
echo ""

# =========================================================================
# PHASE 5: Key Vault Secrets User role (backup for identity.bicep)
# =========================================================================
# identity.bicep assigns this via Bicep, but may fail with RoleAssignmentExists
# if previously assigned manually with a different GUID name. This CLI step
# ensures the role is always present regardless of Bicep module success.
echo "--- Phase 5: Ensuring Key Vault Secrets User role ---"
KV_ID=$(az keyvault show --name "$KV_NAME" --query id -o tsv 2>/dev/null || echo "")
if [ -n "$KV_ID" ]; then
    EXISTING_KV_ROLE=$(az role assignment list --assignee "$PRINCIPAL_ID" --role "Key Vault Secrets User" --scope "$KV_ID" --query "length(@)" -o tsv 2>/dev/null || echo "0")
    if [ "${EXISTING_KV_ROLE:-0}" -gt 0 ] 2>/dev/null; then
        echo "Key Vault Secrets User: already assigned"
    else
        az role assignment create --assignee "$PRINCIPAL_ID" --role "Key Vault Secrets User" --scope "$KV_ID" --output none
        echo "Key Vault Secrets User: assigned"
    fi
else
    echo "WARNING: Key Vault '${KV_NAME}' not found — skipping role assignment"
fi
echo ""

# =========================================================================
# PHASE 6: Re-deploy Bicep if first attempt failed
# =========================================================================
if [ "$BICEP_OK" = false ]; then
    echo "--- Phase 6: Re-deploying Bicep (AcrPull + KV roles now assigned) ---"
    if ! az deployment group create \
        --resource-group "$RESOURCE_GROUP" \
        --template-file "${SCRIPT_DIR}/main.bicep" \
        --parameters "$PARAM_FILE" \
        --output none 2>&1; then
        echo "WARNING: Re-deploy had partial failures"
        echo "(identity/alerts modules may report RoleAssignmentExists or missing KQL tables — benign)"
    fi
    echo ""
fi

# =========================================================================
# PHASE 7: RBAC propagation wait + force revision (greenfield only)
# =========================================================================
# On greenfield, Key Vault RBAC takes 5-10 min to propagate. The container
# revision created by Bicep will fail to resolve KV secret references because
# RBAC hasn't propagated yet. The K8s secret (capp-<app-name>) is never
# created, and Azure does NOT retry. We must wait, then force a new revision.
if [ "$GREENFIELD" = true ]; then
    echo "--- Phase 7: Waiting for Key Vault RBAC propagation ---"
    echo "Waiting 180 seconds for RBAC to propagate..."
    sleep 180

    echo "Forcing new revision to pick up Key Vault secrets..."
    az containerapp update -n "$APP_NAME" -g "$RESOURCE_GROUP" \
        --set-env-vars "RESTART_TRIGGER=deploy-$(date +%s)" \
        --output none
    echo "Revision restart triggered"
    echo ""
fi

# =========================================================================
# PHASE 8: CORS update (greenfield only)
# =========================================================================
# On greenfield, the FQDN isn't known until after the Container App Environment
# is created (includes a random hash). Bicep sets CORS from the param file,
# which may have a placeholder. Override with the actual FQDN via env var.
FQDN=$(az containerapp show -n "$APP_NAME" -g "$RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv)
if [ "$GREENFIELD" = true ]; then
    echo "--- Phase 8: Configuring CORS ---"
    az containerapp update -n "$APP_NAME" -g "$RESOURCE_GROUP" \
        --set-env-vars "CORS_ORIGINS=https://${FQDN}" \
        --output none
    echo "CORS set to https://${FQDN}"
    echo ""
fi

# =========================================================================
# PHASE 9: SPA redirect URIs (greenfield only)
# =========================================================================
# Register both the base URL and /auth/callback. MSAL uses window.location.origin
# as redirect URI, so both must be registered or login fails with AADSTS50011.
if [ "$GREENFIELD" = true ] && [ -n "$CLIENT_ID" ]; then
    echo "--- Phase 9: Registering SPA redirect URIs ---"
    if az ad app update --id "$CLIENT_ID" \
        --set spa="{\"redirectUris\":[\"https://${FQDN}\",\"https://${FQDN}/auth/callback\",\"http://localhost:5173\",\"http://localhost:5173/auth/callback\"]}" 2>/dev/null; then
        echo "SPA redirect URIs registered for https://${FQDN}"
    else
        echo "WARNING: Could not update SPA redirect URIs (may require higher permissions)"
        echo "Manual step:"
        echo "  az ad app update --id $CLIENT_ID \\"
        echo "    --set spa='{\"redirectUris\":[\"https://${FQDN}\",\"https://${FQDN}/auth/callback\"]}'"
    fi
    echo ""
fi

# =========================================================================
# PHASE 10: Health check
# =========================================================================
# SKIP_HEALTH_CHECK=1 can be set by callers (e.g. deploy-new-client.sh) that
# run their own health check after DB init. On greenfield, the readiness probe
# fails before schema exists, causing KEDA scale-to-zero and 7+ min timeouts.
if [ "${SKIP_HEALTH_CHECK:-}" = "1" ]; then
    echo "--- Phase 10: Health check SKIPPED (caller will run post-DB-init) ---"
else
    echo "--- Phase 10: Health check ---"
    echo "URL: https://${FQDN}/health/ready"
    RETRIES=0
    MAX_RETRIES=12
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
        echo ""
        echo "WARNING: Health check did not pass after $((MAX_RETRIES * 10)) seconds"
        echo "Check container logs:"
        echo "  az containerapp logs show -n $APP_NAME -g $RESOURCE_GROUP --type system"
    fi
fi
echo ""

# =========================================================================
# SUMMARY
# =========================================================================
echo "=== Deployment Complete ==="
echo "Environment:  ${ENV}"
echo "Container:    ${APP_NAME}"
echo "URL:          https://${FQDN}"
echo "Health:       https://${FQDN}/health/ready"
echo "MCP:          https://${FQDN}/mcp"
echo ""

if [ "$GREENFIELD" = true ]; then
    echo "=== NEXT STEPS ==="
    echo ""
    echo "Infrastructure provisioned. To complete client setup (database, token,"
    echo "CORS writeback), use the full orchestration script:"
    echo ""
    echo "  ./infra/deploy-new-client.sh ${ENV} ${IMAGE_TAG}"
    echo ""
    echo "Or complete manually (resource names depend on CAF vs legacy naming):"
    echo "  1. DB init: sqlcmd -S <sql-server>.database.windows.net -d <database> \\"
    echo "       -G --authentication-method=ActiveDirectoryDefault -i schema.sql"
    echo "  2. Migrations: cd server && uv run python -m scripts.migrate \\"
    echo "       --server <sql-server>.database.windows.net --database <database>"
    echo "  3. Token: cd server && uv run python scripts/manage_tokens.py create \\"
    echo "       --client '${ENV}' --email '<client-email>'"
    echo "  4. Admin consent (requires Global Admin):"
    echo "     Azure Portal > App Registrations > ${CLIENT_ID} > API Permissions"
    echo ""
fi
