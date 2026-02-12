#!/bin/bash
set -euo pipefail

# =============================================================================
# deploy-all.sh — Deploy Meeting Intelligence to multiple environments
# =============================================================================
#
# Usage:
#   ./infra/deploy-all.sh [image-tag]
#   ./infra/deploy-all.sh [image-tag] --skip-audit
#
# Reads environments from the list below and deploys in order:
#   1. Internal environments first (team, demo) — canary
#   2. Client environments (marshall, etc.) — staged rollout
#
# Each deployment:
#   - Runs audit (unless --skip-audit)
#   - Builds and pushes container image (once, shared tag)
#   - Deploys Bicep templates
#   - Health-checks after deployment
#   - Stops on first failure
#
# Prerequisites:
#   - Azure CLI authenticated
#   - .env.deploy with secrets
#   - Docker/ACR access

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

IMAGE_TAG=${1:-$(date +%Y%m%d%H%M%S)}
SKIP_AUDIT=false

for arg in "$@"; do
    case $arg in
        --skip-audit) SKIP_AUDIT=true ;;
    esac
done

# === ENVIRONMENT ORDER ===
# Internal environments deploy first (canary).
# Client environments deploy after internal passes.
INTERNAL_ENVS=("team")
CLIENT_ENVS=("marshall")
# Add new environments here:
# CLIENT_ENVS=("marshall" "client2" "client3")

ACR_NAME="meetingintelacr20260116"

echo "=== Multi-Environment Deployment ==="
echo "Image Tag: ${IMAGE_TAG}"
echo "Internal: ${INTERNAL_ENVS[*]}"
echo "Client:   ${CLIENT_ENVS[*]}"
echo ""

# --- Pre-flight: Audit ---
if [ "$SKIP_AUDIT" = false ]; then
    echo "--- Running vulnerability audit ---"
    if ! "${SCRIPT_DIR}/audit.sh"; then
        echo ""
        echo "ABORT: Audit failed. Fix vulnerabilities or use --skip-audit"
        exit 1
    fi
    echo ""
fi

# --- Pre-flight: Build and push image ---
echo "--- Building container image ---"
echo "Building mi:${IMAGE_TAG} via ACR..."
az acr build \
    --registry "$ACR_NAME" \
    --image "mi:${IMAGE_TAG}" \
    --file "${REPO_ROOT}/server/Dockerfile" \
    "${REPO_ROOT}/server" \
    --no-logs 2>&1 | tail -5
echo "Image pushed: ${ACR_NAME}.azurecr.io/mi:${IMAGE_TAG}"
echo ""

# --- Load secrets ---
if [ -f "${REPO_ROOT}/.env.deploy" ]; then
    set -a
    source "${REPO_ROOT}/.env.deploy"
    set +a
fi

if [ -z "${JWT_SECRET:-}" ]; then
    read -sp "JWT_SECRET: " JWT_SECRET; echo
fi

# --- Deploy function ---
deploy_env() {
    local env_name=$1
    local rg="meeting-intelligence-${env_name}-rg"
    local param_file="${SCRIPT_DIR}/parameters/${env_name}.bicepparam"

    echo "--- Deploying: ${env_name} ---"

    if [ ! -f "$param_file" ]; then
        echo "  SKIP: No parameter file at ${param_file}"
        return 1
    fi

    # For environments using readEnvironmentVariable() in bicepparam
    export CONTAINER_IMAGE_TAG="${IMAGE_TAG}"

    az group create \
        --name "$rg" \
        --location "australiaeast" \
        --tags environment="$env_name" project=meeting-intelligence \
        --output none 2>/dev/null

    if az deployment group create \
        --resource-group "$rg" \
        --template-file "${SCRIPT_DIR}/main.bicep" \
        --parameters "$param_file" \
        --parameters containerImageTag="$IMAGE_TAG" \
        --parameters jwtSecret="$JWT_SECRET" \
        --parameters appInsightsConnection="${APPLICATIONINSIGHTS_CONNECTION_STRING:-}" \
        --output none 2>&1; then
        echo "  Deploy: OK"
    else
        echo "  Deploy: FAILED"
        return 1
    fi

    # Health check
    local fqdn
    fqdn=$(az deployment group show \
        --resource-group "$rg" \
        --name main \
        --query "properties.outputs.containerAppFqdn.value" \
        -o tsv 2>/dev/null || echo "")

    if [ -n "$fqdn" ]; then
        echo "  Health check: https://${fqdn}/health/ready"
        local retries=0
        local max_retries=6
        while [ $retries -lt $max_retries ]; do
            if curl -sf "https://${fqdn}/health/ready" > /dev/null 2>&1; then
                echo "  Health: OK"
                return 0
            fi
            retries=$((retries + 1))
            echo "  Health: waiting... (${retries}/${max_retries})"
            sleep 10
        done
        echo "  Health: FAILED after ${max_retries} attempts"
        return 1
    else
        echo "  Health: Could not determine FQDN (check deployment outputs)"
        return 1
    fi
}

# --- Deploy internal environments (canary) ---
FAILED=false
for env in "${INTERNAL_ENVS[@]}"; do
    if ! deploy_env "$env"; then
        echo ""
        echo "ABORT: Internal deployment failed for ${env}. Not proceeding to client environments."
        FAILED=true
        break
    fi
    echo ""
done

if [ "$FAILED" = true ]; then
    exit 1
fi

# --- Deploy client environments (staged) ---
for env in "${CLIENT_ENVS[@]}"; do
    if ! deploy_env "$env"; then
        echo ""
        echo "ABORT: Client deployment failed for ${env}. Stopping rollout."
        echo "Already deployed: ${INTERNAL_ENVS[*]}"
        FAILED=true
        break
    fi
    echo ""
done

# --- Summary ---
echo "=== Deployment Summary ==="
if [ "$FAILED" = true ]; then
    echo "RESULT: Partial deployment — check logs above"
    exit 1
else
    echo "RESULT: All environments deployed successfully"
    echo "Image: mi:${IMAGE_TAG}"
    exit 0
fi
