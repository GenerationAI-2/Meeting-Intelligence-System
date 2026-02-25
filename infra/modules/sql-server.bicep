// sql-server.bicep — SQL Server + Control DB + General Workspace DB
// Part of Meeting Intelligence IaC — P7 Workspace Architecture
//
// Creates three resources:
//   1. SQL Server with Entra-only auth
//   2. Control database (workspaces, users, tokens, audit)
//   3. General workspace database (meetings, actions, decisions)
//
// For adding additional workspace databases, use workspace-db.bicep.

@description('Environment name')
param environmentName string

@description('Azure region')
param location string

@description('Resource tags')
param tags object

@description('Azure AD admin object ID for SQL Server')
param sqlAdminObjectId string

@description('Azure AD admin display name')
param sqlAdminDisplayName string = 'Caleb Lucas'

@description('Database SKU name')
param databaseSkuName string = 'Basic'

@description('Database SKU tier')
param databaseSkuTier string = 'Basic'

@description('Database max size in bytes (2GB = 2147483648)')
param databaseMaxSizeBytes int = 2147483648

@description('Log Analytics workspace resource ID for diagnostic settings')
param logAnalyticsWorkspaceId string

// === SQL SERVER ===

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: 'mi-${environmentName}-sql'
  location: location
  tags: tags
  properties: {
    administrators: {
      administratorType: 'ActiveDirectory'
      login: sqlAdminDisplayName
      sid: sqlAdminObjectId
      tenantId: subscription().tenantId
      azureADOnlyAuthentication: true
      principalType: 'User'
    }
    minimalTlsVersion: '1.2'
  }
}

// === FIREWALL: Allow Azure Services ===

resource firewallAllowAzure 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  parent: sqlServer
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// === CONTROL DATABASE ===

resource controlDatabase 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: 'mi-${environmentName}-control'
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

// === GENERAL WORKSPACE DATABASE ===

resource generalDatabase 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: 'mi-${environmentName}'
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

// === AUDITING ===

resource sqlAuditing 'Microsoft.Sql/servers/auditingSettings@2023-08-01-preview' = {
  parent: sqlServer
  name: 'default'
  properties: {
    state: 'Enabled'
    isAzureMonitorTargetEnabled: true
    retentionDays: 90
  }
}

// === TRANSPARENT DATA ENCRYPTION ===

resource tdeControl 'Microsoft.Sql/servers/databases/transparentDataEncryption@2023-08-01-preview' = {
  parent: controlDatabase
  name: 'current'
  properties: {
    state: 'Enabled'
  }
}

resource tdeGeneral 'Microsoft.Sql/servers/databases/transparentDataEncryption@2023-08-01-preview' = {
  parent: generalDatabase
  name: 'current'
  properties: {
    state: 'Enabled'
  }
}

// === DIAGNOSTIC SETTINGS ===

var sqlDiagLogs = [
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

var sqlDiagMetrics = [
  { category: 'Basic', enabled: true }
  { category: 'InstanceAndAppAdvanced', enabled: true }
  { category: 'WorkloadManagement', enabled: true }
]

resource controlDatabaseDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'mi-${environmentName}-control-sql-diag'
  scope: controlDatabase
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: sqlDiagLogs
    metrics: sqlDiagMetrics
  }
}

resource generalDatabaseDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'mi-${environmentName}-sql-diag'
  scope: generalDatabase
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: sqlDiagLogs
    metrics: sqlDiagMetrics
  }
}

// === OUTPUTS ===

output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName
output sqlServerName string = sqlServer.name
output sqlDatabaseName string = generalDatabase.name
output controlDbName string = controlDatabase.name
