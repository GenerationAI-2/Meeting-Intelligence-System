#!/bin/bash
set -euo pipefail

# =============================================================================
# deploy-bicep.sh — Deploy Meeting Intelligence via Bicep IaC
# =============================================================================
#
# Usage:
#   ./infra/deploy-bicep.sh <environment-name> [image-tag]
#
# Examples:
#   ./infra/deploy-bicep.sh team 20260209143022
#   ./infra/deploy-bicep.sh demo                  # auto-generates timestamp tag
#   ./infra/deploy-bicep.sh bicep-test             # test environment
#
# Prerequisites:
#   - Azure CLI authenticated (az login)
#   - Bicep CLI installed (az bicep install)
#   - .env.deploy file with secrets (or export them)
#   - Docker image already built and pushed to ACR
#     (use: az acr build --registry meetingintelacr20260116 ...)

ENV=${1:?Usage: ./infra/deploy-bicep.sh <environment-name> [image-tag]}
IMAGE_TAG=${2:-$(date +%Y%m%d%H%M%S)}
RESOURCE_GROUP="meeting-intelligence-${ENV}-rg"
LOCATION="australiaeast"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Deploying Meeting Intelligence: ${ENV} ==="
echo "Resource Group: ${RESOURCE_GROUP}"
echo "Image Tag: ${IMAGE_TAG}"
echo ""

# Load secrets from .env.deploy if available
if [ -f "${SCRIPT_DIR}/../.env.deploy" ]; then
    echo "Loading secrets from .env.deploy..."
    set -a
    source "${SCRIPT_DIR}/../.env.deploy"
    set +a
fi

# Prompt for secrets if not already set
if [ -z "${JWT_SECRET:-}" ]; then
    read -sp "JWT_SECRET: " JWT_SECRET; echo
fi

# Export env vars for readEnvironmentVariable() in .bicepparam files
export CONTAINER_IMAGE_TAG="$IMAGE_TAG"
export JWT_SECRET
export APPLICATIONINSIGHTS_CONNECTION_STRING="${APPLICATIONINSIGHTS_CONNECTION_STRING:-}"

# Validate parameter file exists
PARAM_FILE="${SCRIPT_DIR}/parameters/${ENV}.bicepparam"
if [ ! -f "$PARAM_FILE" ]; then
    echo "WARNING: No parameter file at ${PARAM_FILE}"
    echo "Using team.bicepparam as base"
    PARAM_FILE="${SCRIPT_DIR}/parameters/team.bicepparam"
fi

# Create resource group with tags
echo ""
echo "--- Creating resource group ---"
az group create \
    --name "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --tags environment="$ENV" project=meeting-intelligence owner=caleb.lucas@accretiveai.com created-by=bicep \
    --output none

# Deploy Bicep
echo ""
echo "--- Deploying Bicep templates ---"
az deployment group create \
    --resource-group "$RESOURCE_GROUP" \
    --template-file "${SCRIPT_DIR}/main.bicep" \
    --parameters "$PARAM_FILE" \
    --verbose

# Output results
echo ""
echo "=== Deployment Complete ==="
az deployment group show \
    --resource-group "$RESOURCE_GROUP" \
    --name main \
    --query "properties.outputs" \
    -o table

# Post-deployment instructions
CONTAINER_APP_NAME=$(az deployment group show \
    --resource-group "$RESOURCE_GROUP" \
    --name main \
    --query "properties.outputs.containerAppName.value" \
    -o tsv 2>/dev/null || echo "mi-${ENV}")

echo ""
echo "=== POST-DEPLOYMENT STEPS ==="
echo ""
echo "1. Grant Container App managed identity access to SQL:"
echo "   Connect to the SQL database and run:"
echo ""
echo "   CREATE USER [${CONTAINER_APP_NAME}] FROM EXTERNAL PROVIDER;"
echo "   ALTER ROLE db_datareader ADD MEMBER [${CONTAINER_APP_NAME}];"
echo "   ALTER ROLE db_datawriter ADD MEMBER [${CONTAINER_APP_NAME}];"
echo ""
echo "2. Grant ACR Pull to Container App identity (if not already):"
echo "   PRINCIPAL_ID=\$(az containerapp show -n ${CONTAINER_APP_NAME} -g ${RESOURCE_GROUP} --query identity.principalId -o tsv)"
echo "   ACR_ID=\$(az acr show -n meetingintelacr20260116 --query id -o tsv)"
echo "   az role assignment create --assignee \$PRINCIPAL_ID --role AcrPull --scope \$ACR_ID"
echo ""
echo "3. Verify health:"
echo "   curl -s https://\$(az containerapp show -n ${CONTAINER_APP_NAME} -g ${RESOURCE_GROUP} --query properties.configuration.ingress.fqdn -o tsv)/health/ready"
