#!/bin/bash
# Enable Azure SQL Auditing for Meeting Intelligence
#
# This script enables server-level auditing on the Azure SQL server.
# Audit logs are stored in Azure Log Analytics for centralized monitoring.
#
# Prerequisites:
# - Azure CLI installed and logged in
# - Contributor access to the SQL server resource group
#
# Usage:
#   ./scripts/enable-sql-auditing.sh

set -e

# Configuration
SQL_SERVER="genai-sql-server"
SQL_RG="rg-generationAI-Internal"
LOG_ANALYTICS_WORKSPACE="genai-logs"  # Update if different

echo "=========================================="
echo "Enabling Azure SQL Auditing"
echo "Server: $SQL_SERVER"
echo "Resource Group: $SQL_RG"
echo "=========================================="

# Option 1: Enable with Log Analytics (recommended)
# This sends audit logs to Log Analytics for querying and alerting
echo ""
echo "Enabling auditing with Log Analytics..."

# Get Log Analytics workspace ID
WORKSPACE_ID=$(az monitor log-analytics workspace show \
    --resource-group "$SQL_RG" \
    --workspace-name "$LOG_ANALYTICS_WORKSPACE" \
    --query id -o tsv 2>/dev/null || echo "")

if [ -n "$WORKSPACE_ID" ]; then
    echo "Using Log Analytics workspace: $LOG_ANALYTICS_WORKSPACE"

    az sql server audit-policy update \
        --resource-group "$SQL_RG" \
        --name "$SQL_SERVER" \
        --state Enabled \
        --lats Enabled \
        --lawri "$WORKSPACE_ID"

    echo "Auditing enabled with Log Analytics integration"
else
    echo "Log Analytics workspace not found. Enabling auditing with storage fallback..."

    # Option 2: Enable with storage account
    # Creates a storage account for audit logs if Log Analytics not available
    STORAGE_ACCOUNT="genaistorageaudit"

    # Create storage account if it doesn't exist
    az storage account create \
        --name "$STORAGE_ACCOUNT" \
        --resource-group "$SQL_RG" \
        --location australiaeast \
        --sku Standard_LRS \
        --output none 2>/dev/null || true

    az sql server audit-policy update \
        --resource-group "$SQL_RG" \
        --name "$SQL_SERVER" \
        --state Enabled \
        --blob-storage-target-state Enabled \
        --storage-account "$STORAGE_ACCOUNT" \
        --retention-days 90

    echo "Auditing enabled with storage account: $STORAGE_ACCOUNT"
fi

echo ""
echo "=========================================="
echo "Auditing configuration complete!"
echo ""
echo "To verify:"
echo "  az sql server audit-policy show --resource-group $SQL_RG --name $SQL_SERVER"
echo ""
echo "To view audit logs (if using Log Analytics):"
echo "  1. Go to Azure Portal > Log Analytics workspace"
echo "  2. Run query: AzureDiagnostics | where Category == 'SQLSecurityAuditEvents'"
echo "=========================================="
