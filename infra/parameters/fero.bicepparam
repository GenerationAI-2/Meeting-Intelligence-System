using '../main.bicep'

// --- CAF naming ---
param cafNaming = true
param environmentType = 'prod'

// --- Client identity ---
param environmentName = 'fero'
param location = 'newzealandnorth'
param acrName = 'meetingintelacr20260116'

// --- SQL admin ---
param sqlAdminObjectId = 'dff4aa0e-e9b5-4060-9a88-4947c5903b99'
param sqlAdminDisplayName = 'Caleb Lucas'

// --- Azure AD auth ---
param azureTenantId = '12e7fcaa-f776-4545-aacf-e89be7737cf3'
param azureClientId = 'eb7a3e22-cefc-4815-965c-ba675e483de0'

// --- Access control ---
param allowedUsers = 'sam@fero.co.nz,caleb.lucas@generationai.co.nz'
param corsOrigins = 'https://placeholder'     // Updated automatically by deploy-new-client.sh Phase 4
param minReplicas = 1

// --- Dynamic params (passed via environment variables at deploy time) ---
param containerImageTag = readEnvironmentVariable('CONTAINER_IMAGE_TAG', 'latest')
param appInsightsConnection = readEnvironmentVariable('APPLICATIONINSIGHTS_CONNECTION_STRING', '')
