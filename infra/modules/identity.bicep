// identity.bicep — Role assignments for Container App managed identity
// Part of Meeting Intelligence IaC (Stream A)
//
// Grants:
// - Key Vault Secrets User (read secrets from Key Vault)
//
// Idempotency note:
//   The role assignment uses a deterministic GUID name based on (keyVault.id,
//   principalId, roleDefinitionId). Re-deploying with the same inputs produces
//   the same name, so Azure treats it as an update (idempotent).
//
//   However, if the same role was previously assigned MANUALLY (with a different
//   GUID name), this module will fail with RoleAssignmentExists. This is benign —
//   the role IS assigned. deploy-bicep.sh Phase 5 ensures the role via CLI as a
//   backup, so overall deployment succeeds regardless.
//
// NOT handled here:
// - ACR Pull: ACR is in a different resource group — handled by deploy-bicep.sh Phase 4
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
