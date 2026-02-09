// identity.bicep — Role assignments for Container App managed identity
// Part of Meeting Intelligence IaC (Stream A)
//
// Grants:
// - Key Vault Secrets User (read secrets from Key Vault)
//
// NOT handled here:
// - ACR Pull: handled automatically by Container Apps managed identity registry
// - SQL access: must be done via SQL after deployment (CREATE USER FROM EXTERNAL PROVIDER)

@description('Container App system-assigned managed identity principal ID')
param containerAppPrincipalId string

@description('Key Vault name to grant access to')
param keyVaultName string

// === EXISTING RESOURCES ===

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

// === ROLE DEFINITIONS ===
// Key Vault Secrets User: 4633458b-17de-408a-b874-0445c86b69e6

var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

// === ROLE ASSIGNMENTS ===

resource kvSecretsUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, containerAppPrincipalId, keyVaultSecretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: containerAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}
