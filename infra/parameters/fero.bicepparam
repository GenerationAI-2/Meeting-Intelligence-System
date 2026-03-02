using '../main.bicep'

// --- CAF naming ---
param cafNaming = true
param environmentType = 'prod'

// --- Subscription (read by deploy-bicep.sh via grep, not a Bicep param) ---
// param subscriptionId = '477efa0e-642d-4ed6-ace7-5210e60ed024'

// --- Client identity ---
param environmentName = 'fero'
param location = 'australiaeast'
param acrName = 'meetingintelacr20260116'

// --- SQL admin ---
param sqlAdminObjectId = 'dff4aa0e-e9b5-4060-9a88-4947c5903b99'
param sqlAdminDisplayName = 'Caleb Lucas'

// --- Azure AD auth ---
param azureTenantId = '12e7fcaa-f776-4545-aacf-e89be7737cf3'
param azureClientId = 'eb7a3e22-cefc-4815-965c-ba675e483de0'

// --- Access control ---
param allowedUsers = 'sam@fero.co.nz,caleb.lucas@generationai.co.nz'
param corsOrigins = 'https://ca-mi-prod-fero.kindmushroom-a2d43986.australiaeast.azurecontainerapps.io'     // Updated automatically by deploy-new-client.sh Phase 4
param minReplicas = 1

// --- Dynamic params (passed via environment variables at deploy time) ---
param containerImageTag = readEnvironmentVariable('CONTAINER_IMAGE_TAG', 'latest')
param appInsightsConnection = readEnvironmentVariable('APPLICATIONINSIGHTS_CONNECTION_STRING', '')
