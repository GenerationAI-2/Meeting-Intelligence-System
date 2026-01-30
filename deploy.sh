#!/bin/bash
set -e

# =============================================================================
# CONFIGURATION
# =============================================================================

ENV="${1:-dev}"

# =============================================================================
# PHASE 2 RESTRICTION: Prod deployment blocked
# Remove this block after Phase 2 is complete and approved.
# =============================================================================
if [ "$ENV" == "prod" ]; then
    echo "=============================================="
    echo "BLOCKED: Prod deployment disabled"
    echo "=============================================="
    echo "Phase 2 work targets DEV only."
    echo "Current prod must remain untouched until sign-off."
    echo ""
    echo "To deploy to dev:  ./deploy.sh dev"
    echo "To remove block:   Edit deploy.sh after Phase 2 approval"
    echo "=============================================="
    exit 1
fi

# Load local secrets if available (gitignored)
if [ -f .env.deploy ]; then
    echo "Loading secrets from .env.deploy..."
    set -a
    source .env.deploy
    set +a
fi

# Required secrets (fail fast if not set)
: "${MCP_AUTH_TOKENS:?MCP_AUTH_TOKENS must be set (export or .env.deploy)}"
: "${ALLOWED_USERS:?ALLOWED_USERS must be set}"
: "${CORS_ORIGINS:?CORS_ORIGINS must be set}"

# Environment-specific config
case "$ENV" in
    prod)
        RG="meeting-intelligence-prod-rg"
        APP_NAME="meeting-intelligence"
        DB_NAME="meeting-intelligence"
        ;;
    dev)
        RG="meeting-intelligence-dev-rg"
        APP_NAME="meeting-intelligence-dev"
        DB_NAME="meeting-intelligence-dev"
        ;;
    team)
        RG="meeting-intelligence-team-rg"
        APP_NAME="meeting-intelligence-team"
        DB_NAME="meeting-intelligence-team"
        ;;
    *)
        echo "Usage: ./deploy.sh [dev|prod|team]"
        exit 1
        ;;
esac

# Shared config
LOCATION="australiaeast"
ACR_NAME="meetingintelacr20260116"
ACA_ENV="genai-env"

# Azure AD (same for all envs currently)
VITE_SPA_CLIENT_ID="${VITE_SPA_CLIENT_ID:-d38c25fa-3ce8-4648-87ab-079dcc52754b}"
VITE_API_CLIENT_ID="${VITE_API_CLIENT_ID:-b5a8a565-e18e-42a6-a57b-ade6d17aa197}"
VITE_AZURE_TENANT_ID="${VITE_AZURE_TENANT_ID:-12e7fcaa-f776-4545-aacf-e89be7737cf3}"
API_AZURE_TENANT_ID="${API_AZURE_TENANT_ID:-$VITE_AZURE_TENANT_ID}"
API_AZURE_CLIENT_ID="${API_AZURE_CLIENT_ID:-$VITE_API_CLIENT_ID}"

# Database
AZURE_SQL_SERVER="${AZURE_SQL_SERVER:-genai-sql-server.database.windows.net}"
AZURE_SQL_DATABASE="${AZURE_SQL_DATABASE:-$DB_NAME}"

# Image tag from git
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"

echo "=========================================="
echo "Deploying: $ENV"
echo "Resource Group: $RG"
echo "App Name: $APP_NAME"
echo "Database: $AZURE_SQL_DATABASE"
echo "Image Tag: $IMAGE_TAG"
echo "=========================================="

# =============================================================================
# DEPLOYMENT
# =============================================================================

# 1. Ensure Resource Group exists
az group create --name "$RG" --location "$LOCATION" --output none

# 2. Ensure Container Registry exists
az acr create --resource-group "$RG" --name "$ACR_NAME" --sku Basic --admin-enabled true --output none 2>/dev/null || true

# 3. Build and push image
echo "Building image..."
az acr build --registry "$ACR_NAME" --image "$APP_NAME:$IMAGE_TAG" \
    --file server/Dockerfile \
    --build-arg VITE_SPA_CLIENT_ID="$VITE_SPA_CLIENT_ID" \
    --build-arg VITE_API_CLIENT_ID="$VITE_API_CLIENT_ID" \
    --build-arg VITE_AZURE_TENANT_ID="$VITE_AZURE_TENANT_ID" \
    --build-arg VITE_API_URL="/api" \
    .

# 4. Create or update Container App
echo "Deploying container app..."
if az containerapp show --name "$APP_NAME" --resource-group "$RG" &>/dev/null; then
    # Update existing
    az containerapp update \
        --name "$APP_NAME" \
        --resource-group "$RG" \
        --image "$ACR_NAME.azurecr.io/$APP_NAME:$IMAGE_TAG" \
        --set-env-vars \
            AZURE_SQL_SERVER="$AZURE_SQL_SERVER" \
            AZURE_SQL_DATABASE="$AZURE_SQL_DATABASE" \
            MCP_AUTH_TOKENS="$MCP_AUTH_TOKENS" \
            API_AZURE_TENANT_ID="$API_AZURE_TENANT_ID" \
            API_AZURE_CLIENT_ID="$API_AZURE_CLIENT_ID" \
            ALLOWED_USERS="$ALLOWED_USERS" \
            CORS_ORIGINS="$CORS_ORIGINS"
else
    # Create new
    az containerapp env create --name "$ACA_ENV" --resource-group "$RG" --location "$LOCATION" --output none 2>/dev/null || true

    az containerapp create \
        --name "$APP_NAME" \
        --resource-group "$RG" \
        --environment "$ACA_ENV" \
        --image "$ACR_NAME.azurecr.io/$APP_NAME:$IMAGE_TAG" \
        --target-port 8000 \
        --ingress external \
        --min-replicas 1 \
        --registry-server "$ACR_NAME.azurecr.io" \
        --system-assigned \
        --env-vars \
            AZURE_SQL_SERVER="$AZURE_SQL_SERVER" \
            AZURE_SQL_DATABASE="$AZURE_SQL_DATABASE" \
            MCP_AUTH_TOKENS="$MCP_AUTH_TOKENS" \
            API_AZURE_TENANT_ID="$API_AZURE_TENANT_ID" \
            API_AZURE_CLIENT_ID="$API_AZURE_CLIENT_ID" \
            ALLOWED_USERS="$ALLOWED_USERS" \
            CORS_ORIGINS="$CORS_ORIGINS"
fi

# 5. Output results
APP_URL=$(az containerapp show --name "$APP_NAME" --resource-group "$RG" --query properties.configuration.ingress.fqdn -o tsv)
echo ""
echo "=========================================="
echo "Deployment complete!"
echo "URL: https://$APP_URL"
echo "=========================================="
