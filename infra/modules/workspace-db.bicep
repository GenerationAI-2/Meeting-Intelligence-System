// workspace-db.bicep — Single workspace database on an existing SQL Server
// Part of Meeting Intelligence IaC — P7 Workspace Architecture
//
// Use this module to add a workspace database to an existing server.
// For initial provisioning (server + control + general), use sql-server.bicep.

@description('Existing SQL Server resource name')
param sqlServerName string

@description('Workspace database name (e.g., mi-marshall-board)')
param databaseName string

@description('Azure region')
param location string

@description('Resource tags')
param tags object

@description('Database SKU name')
param databaseSkuName string = 'Basic'

@description('Database SKU tier')
param databaseSkuTier string = 'Basic'

@description('Database max size in bytes (2GB = 2147483648)')
param databaseMaxSizeBytes int = 2147483648

@description('Log Analytics workspace resource ID for diagnostic settings')
param logAnalyticsWorkspaceId string

// === EXISTING SERVER REFERENCE ===

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' existing = {
  name: sqlServerName
}

// === WORKSPACE DATABASE ===

resource workspaceDatabase 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: databaseName
  location: location
  tags: tags
  sku: {
    name: databaseSkuName
    tier: databaseSkuTier
  }
  properties: {
    maxSizeBytes: databaseMaxSizeBytes
    collation: 'SQL_Latin1_General_CP1_CI_AS'
  }
}

// === TRANSPARENT DATA ENCRYPTION ===

resource tde 'Microsoft.Sql/servers/databases/transparentDataEncryption@2023-08-01-preview' = {
  parent: workspaceDatabase
  name: 'current'
  properties: {
    state: 'Enabled'
  }
}

// === DIAGNOSTIC SETTINGS ===

resource databaseDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: '${databaseName}-sql-diag'
  scope: workspaceDatabase
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      { category: 'SQLInsights', enabled: true }
      { category: 'AutomaticTuning', enabled: true }
      { category: 'QueryStoreRuntimeStatistics', enabled: true }
      { category: 'QueryStoreWaitStatistics', enabled: true }
      { category: 'Errors', enabled: true }
      { category: 'DatabaseWaitStatistics', enabled: true }
      { category: 'Timeouts', enabled: true }
      { category: 'Blocks', enabled: true }
      { category: 'Deadlocks', enabled: true }
      { category: 'DevOpsOperationsAudit', enabled: true }
      { category: 'SQLSecurityAuditEvents', enabled: true }
    ]
    metrics: [
      { category: 'Basic', enabled: true }
      { category: 'InstanceAndAppAdvanced', enabled: true }
      { category: 'WorkloadManagement', enabled: true }
    ]
  }
}

// === OUTPUTS ===

output databaseName string = workspaceDatabase.name
