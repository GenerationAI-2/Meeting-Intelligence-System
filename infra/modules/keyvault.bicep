// keyvault.bicep — Key Vault with RBAC authorization
// Part of Meeting Intelligence IaC (Stream A)
// Stores: APPLICATIONINSIGHTS_CONNECTION_STRING
// See ADR-014 for rationale

@description('Key Vault name')
param keyVaultName string

@description('Azure region')
param location string

@description('Resource tags')
param tags object

@description('Application Insights connection string')
@secure()
param appInsightsConnection string

// === KEY VAULT ===

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
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
output appInsightsSecretUri string = appInsightsSecret.properties.secretUri
