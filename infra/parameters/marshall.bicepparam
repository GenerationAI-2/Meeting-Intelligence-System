using '../main.bicep'

param environmentName = 'marshall'
param location = 'australiaeast'
param acrName = 'meetingintelacr20260116'
param sqlAdminObjectId = 'dff4aa0e-e9b5-4060-9a88-4947c5903b99'
param sqlAdminDisplayName = 'Caleb Lucas'
param azureTenantId = '12e7fcaa-f776-4545-aacf-e89be7737cf3'
param azureClientId = '90ce0113-054d-494d-a4e9-fcf8f0f9d07d'
param allowedUsers = 'john.marshall@myadvisor.co.nz,caleb.lucas@generationai.co.nz'
param corsOrigins = 'https://mi-marshall.delightfulpebble-aa90cd5c.australiaeast.azurecontainerapps.io'
param minReplicas = 1

// Dynamic params — passed via environment variables at deployment time
param containerImageTag = readEnvironmentVariable('CONTAINER_IMAGE_TAG', 'latest')
param jwtSecret = readEnvironmentVariable('JWT_SECRET')
param appInsightsConnection = readEnvironmentVariable('APPLICATIONINSIGHTS_CONNECTION_STRING', '')
