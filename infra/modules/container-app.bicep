// container-app.bicep — Container App + Environment + scaling + health probes
// Part of Meeting Intelligence IaC (Stream A)
// Port: 8000 (NOT 8080 — matches Dockerfile EXPOSE and deploy.sh target-port)
//
// ACR Pull note:
//   The registry config uses identity:'system' which tells Container Apps to use
//   its managed identity for ACR pulls. However, this does NOT create an AcrPull
//   role assignment on the container registry. The ACR (meetingintelacr20260116)
//   lives in a different resource group (meeting-intelligence-v2-rg), making
//   cross-RG role assignment in Bicep complex. Instead, deploy-bicep.sh Phase 4
//   assigns AcrPull via CLI after the Container App is created.

@description('Environment name')
param environmentName string

@description('Azure region')
param location string

@description('Resource tags')
param tags object

@description('ACR name (shared registry)')
param acrName string

@description('Container image tag')
param containerImageTag string

@description('SQL Server FQDN')
param sqlServerFqdn string

@description('SQL Database name')
param sqlDatabaseName string

@description('Azure AD tenant ID')
param azureTenantId string

@description('Azure AD client ID for API auth')
param azureClientId string

@description('Allowed users (comma-separated emails)')
param allowedUsers string

@description('CORS origins (comma-separated URLs)')
param corsOrigins string

@description('Minimum replicas (0 = scale to zero)')
@minValue(0)
@maxValue(10)
param minReplicas int = 0

@description('Key Vault secret URI for App Insights connection string')
param appInsightsConnectionStringSecretUri string

@description('Key Vault secret URI for JWT secret')
param jwtSecretUri string

@description('Control database name (empty = workspace features disabled)')
param controlDbName string = ''

@description('Log Analytics workspace ID for Container Apps Environment')
param logAnalyticsWorkspaceId string

// === CONTAINER APPS ENVIRONMENT ===

resource containerAppEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'mi-${environmentName}-env'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: reference(logAnalyticsWorkspaceId, '2023-09-01').customerId
        sharedKey: listKeys(logAnalyticsWorkspaceId, '2023-09-01').primarySharedKey
      }
    }
  }
}

// === CONTAINER APP ===

var appName = 'mi-${environmentName}'

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        allowInsecure: false
        transport: 'auto'
      }
      registries: [
        {
          server: '${acrName}.azurecr.io'
          identity: 'system'
        }
      ]
      secrets: [
        {
          name: 'jwt-secret'
          keyVaultUrl: jwtSecretUri
          identity: 'system'
        }
        {
          name: 'appinsights-connection'
          keyVaultUrl: appInsightsConnectionStringSecretUri
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: appName
          image: '${acrName}.azurecr.io/${appName}:${containerImageTag}'
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'AZURE_SQL_SERVER', value: sqlServerFqdn }
            { name: 'AZURE_SQL_DATABASE', value: sqlDatabaseName }
            { name: 'CONTROL_DB_NAME', value: controlDbName }
            { name: 'API_AZURE_TENANT_ID', value: azureTenantId }
            { name: 'API_AZURE_CLIENT_ID', value: azureClientId }
            { name: 'ALLOWED_USERS', value: allowedUsers }
            { name: 'CORS_ORIGINS', value: corsOrigins }
            { name: 'JWT_SECRET', secretRef: 'jwt-secret' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection' }
            { name: 'OAUTH_BASE_URL', value: 'https://${appName}.${containerAppEnv.properties.defaultDomain}' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health/live'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health/ready'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: 10
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
}

// === DIAGNOSTIC SETTINGS ===
// Container Apps only expose AllMetrics via diagnosticSettings.
// Console/system logs flow via the Environment's appLogsConfiguration above.

resource containerAppDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'mi-${environmentName}-capp-diag'
  scope: containerApp
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

// === OUTPUTS ===

output fqdn string = containerApp.properties.configuration.ingress.fqdn
output identityPrincipalId string = containerApp.identity.principalId
output containerAppName string = containerApp.name
output containerAppId string = containerApp.id
