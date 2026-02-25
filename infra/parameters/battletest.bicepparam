using '../main.bicep'

param environmentName = 'battletest'
param location = 'australiaeast'
param acrName = 'meetingintelacr20260116'
param sqlAdminObjectId = 'dff4aa0e-e9b5-4060-9a88-4947c5903b99'
param sqlAdminDisplayName = 'Caleb Lucas'
param azureTenantId = '12e7fcaa-f776-4545-aacf-e89be7737cf3'
param azureClientId = 'f2693d2b-5613-43b6-ba30-4cb589654a2a'
param allowedUsers = 'caleb.lucas@generationai.co.nz,mark.lucas@generationai.co.nz'
param corsOrigins = 'https://mi-battletest.whitedune-43b88d45.australiaeast.azurecontainerapps.io'
param minReplicas = 1

// Dynamic params — passed via environment variables at deployment time
param containerImageTag = readEnvironmentVariable('CONTAINER_IMAGE_TAG', 'latest')
param jwtSecret = readEnvironmentVariable('JWT_SECRET')
param appInsightsConnection = readEnvironmentVariable('APPLICATIONINSIGHTS_CONNECTION_STRING', '')
