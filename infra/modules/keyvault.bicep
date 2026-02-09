// keyvault.bicep — Key Vault with RBAC authorization
// Part of Meeting Intelligence IaC (Stream A)
// Stores only: JWT_SECRET and APPLICATIONINSIGHTS_CONNECTION_STRING
// See ADR-014 for rationale

@description('Environment name')
param environmentName string

@description('Azure region')
param location string

@description('Resource tags')
param tags object

@description('JWT secret for OAuth signing')
@secure()
param jwtSecret string

@description('Application Insights connection string')
@secure()
param appInsightsConnection string

// === KEY VAULT ===

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'mi-${environmentName}-kv'
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
  }
}

// === SECRETS ===

resource jwtSecretResource 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'jwt-secret'
  properties: {
    value: jwtSecret
    contentType: 'text/plain'
  }
}

resource appInsightsSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'appinsights-connection'
  properties: {
    value: appInsightsConnection
    contentType: 'text/plain'
  }
}

// === OUTPUTS ===

output keyVaultName string = keyVault.name
output keyVaultId string = keyVault.id
output jwtSecretUri string = jwtSecretResource.properties.secretUri
output appInsightsSecretUri string = appInsightsSecret.properties.secretUri
