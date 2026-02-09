using '../main.bicep'

param environmentName = 'team'
param location = 'australiaeast'
param acrName = 'meetingintelacr20260116'
param sqlAdminObjectId = 'REPLACE_WITH_OBJECT_ID'  // az ad user show --id caleb.lucas@accretiveai.com --query id -o tsv
param sqlAdminDisplayName = 'Caleb Lucas'
param azureTenantId = '12e7fcaa-f776-4545-aacf-e89be7737cf3'
param azureClientId = 'b5a8a565-e18e-42a6-a57b-ade6d17aa197'
param allowedUsers = 'caleb.lucas@accretiveai.com'
param corsOrigins = 'https://meeting-intelligence-team.happystone-42529ebe.australiaeast.azurecontainerapps.io'
param minReplicas = 0

// Secure params passed at deployment time via CLI:
// --parameters jwtSecret=<value>
// --parameters appInsightsConnection=<value>  (optional — auto-generated if empty)
