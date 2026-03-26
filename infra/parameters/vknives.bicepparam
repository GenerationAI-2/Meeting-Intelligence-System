using '../main.bicep'

// --- CAF naming ---
param cafNaming = true
param environmentType = 'prod'

// --- Subscription (read by deploy-bicep.sh via grep, not a Bicep param) ---
// param subscriptionId = '98eaa078-9ce3-47ef-9ea8-322a04012a6f'

// --- Client identity ---
param environmentName = 'vknives'
param location = 'australiaeast'
param acrName = 'meetingintelacr20260116'

// --- SQL admin ---
param sqlAdminObjectId = 'dff4aa0e-e9b5-4060-9a88-4947c5903b99'
param sqlAdminDisplayName = 'Caleb Lucas'

// --- Azure AD auth ---
param azureTenantId = '12e7fcaa-f776-4545-aacf-e89be7737cf3'
param azureClientId = 'ae3e863e-6fda-4830-9573-6a774f0a10b8'

// --- Access control ---
param allowedUsers = 'gareth@victoryknives.co.nz,caleb.lucas@generationai.co.nz'
param corsOrigins = 'https://ca-mi-prod-vknives.happysmoke-3c7c6e93.australiaeast.azurecontainerapps.io,https://victory-knives.claritylayer.co.nz'     // Custom domain added for claritylayer.co.nz
param minReplicas = 0
param keyVaultNameOverride = 'kv-mi-prod-vknives2'    // Original name blocked by soft-delete purge protection in MyAdvisor sub
param faviconPath = '/app/favicons/vknives.png'

// --- Dynamic params (passed via environment variables at deploy time) ---
param containerImageTag = readEnvironmentVariable('CONTAINER_IMAGE_TAG', 'latest')
param appInsightsConnection = readEnvironmentVariable('APPLICATIONINSIGHTS_CONNECTION_STRING', '')
