using '../main.bicep'

param environmentName = 'team'
param location = 'australiaeast'
param acrName = 'meetingintelacr20260116'
param sqlAdminObjectId = 'dff4aa0e-e9b5-4060-9a88-4947c5903b99'
param sqlAdminDisplayName = 'Caleb Lucas'
param azureTenantId = '12e7fcaa-f776-4545-aacf-e89be7737cf3'
param azureClientId = 'b5a8a565-e18e-42a6-a57b-ade6d17aa197'
param allowedUsers = 'caleb.lucas@generationai.co.nz,mark.lucas@generationai.co.nz,eva.trebilco@generationai.co.nz,john.marshall@myadvisor.co.nz'
param corsOrigins = 'https://meeting-intelligence-team.happystone-42529ebe.australiaeast.azurecontainerapps.io'
param minReplicas = 0

// Dynamic params — passed via environment variables at deployment time
param containerImageTag = readEnvironmentVariable('CONTAINER_IMAGE_TAG', 'latest')
param jwtSecret = readEnvironmentVariable('JWT_SECRET')
param appInsightsConnection = readEnvironmentVariable('APPLICATIONINSIGHTS_CONNECTION_STRING', '')
