using '../main.bicep'

param environmentName = 'testing-instance'
param location = 'australiaeast'
param acrName = 'meetingintelacr20260116'
param sqlAdminObjectId = 'dff4aa0e-e9b5-4060-9a88-4947c5903b99'
param sqlAdminDisplayName = 'Caleb Lucas'
param azureTenantId = '12e7fcaa-f776-4545-aacf-e89be7737cf3'
param azureClientId = '291556f7-8e73-4b80-8a20-68dfa999a55c'
param allowedUsers = 'caleb.lucas@generationai.co.nz,mark.lucas@generationai.co.nz'
param corsOrigins = 'https://mi-testing-instance.icycliff-e324f345.australiaeast.azurecontainerapps.io'
param minReplicas = 1

// Dynamic params — passed via environment variables at deployment time
param containerImageTag = readEnvironmentVariable('CONTAINER_IMAGE_TAG', 'latest')
param jwtSecret = readEnvironmentVariable('JWT_SECRET')
param appInsightsConnection = readEnvironmentVariable('APPLICATIONINSIGHTS_CONNECTION_STRING', '')
