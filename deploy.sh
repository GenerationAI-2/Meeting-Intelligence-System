#!/bin/bash
set -e

# Configuration
RG="meeting-intelligence-v2-rg"
LOCATION="australiaeast"
ACR_NAME="meetingintelacr20260116"
ACA_ENV="genai-env"
APP_NAME="meeting-intelligence"

echo "🚀 Starting Deployment to Azure Container Apps..."
echo "Resource Group: $RG"
echo "Location: $LOCATION"

# 1. Create Resource Group
echo "Creating Resource Group..."
az group create --name $RG --location $LOCATION

# 2. Create Container Registry
echo "Creating Azure Container Registry ($ACR_NAME)..."
az acr create --resource-group $RG --name $ACR_NAME --sku Basic --admin-enabled true

# 3. Create Container Apps Environment
echo "Creating Container Apps Environment ($ACA_ENV)..."
az containerapp env create --name $ACA_ENV --resource-group $RG --location $LOCATION

# 4. Build and Push Image
echo "Building and Pushing Docker Image..."
# Use root context (.) to allow access to both web/ and server/ directories
# Pass React Environment Variables as Build Args
az acr build --registry $ACR_NAME --image $APP_NAME:latest \
  --file server/Dockerfile \
  --build-arg VITE_AZURE_CLIENT_ID="d38c25fa-3ce8-4648-87ab-079dcc52754b" \
  --build-arg VITE_AZURE_TENANT_ID="12e7fcaa-f776-4545-aacf-e89be7737cf3" \
  .

# 5. Create/Update Container App
echo "Deploying Container App ($APP_NAME)..."
az containerapp create \
  --name $APP_NAME \
  --resource-group $RG \
  --environment $ACA_ENV \
  --image "$ACR_NAME.azurecr.io/$APP_NAME:latest" \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --registry-server "$ACR_NAME.azurecr.io" \
  --system-assigned \
  --env-vars \
    AZURE_SQL_SERVER="genai-sql-server.database.windows.net" \
    AZURE_SQL_DATABASE="meeting-intelligence" \
    FIREFLIES_API_KEY="aff7c0e4-abdd-4a16-a799-473f6593382a" \
    MCP_AUTH_TOKEN="e5ba95c8bd0fef507c42ddf1a07fee4251c4404c667b6574eecd6219209105e8"

# 6. Get Details
APP_URL=$(az containerapp show --name $APP_NAME --resource-group $RG --query properties.configuration.ingress.fqdn -o tsv)
PRINCIPAL_ID=$(az containerapp identity show --name $APP_NAME --resource-group $RG --query principalId -o tsv)

echo ""
echo "✅ Deployment Successful!"
echo "--------------------------------------------------"
echo "App URL: https://$APP_URL"
echo "SSE Endpoint: https://$APP_URL/sse"
echo "--------------------------------------------------"
echo "⚠️  IMPORTANT: You must grant database access to the Managed Identity."
echo "Identity Principal ID: $PRINCIPAL_ID"
echo "Identity Name: $APP_NAME"
echo ""
echo "Run this SQL command in your database (meeting-intelligence):"
echo "CREATE USER [$APP_NAME] FROM EXTERNAL PROVIDER;"
echo "ALTER ROLE db_datareader ADD MEMBER [$APP_NAME];"
echo "ALTER ROLE db_datawriter ADD MEMBER [$APP_NAME];"
