// monitoring.bicep — Log Analytics + Application Insights + Budget Alerts
// Part of Meeting Intelligence IaC (Stream A)

@description('Environment name')
param environmentName string

@description('Azure region')
param location string

@description('Resource tags')
param tags object

@description('Budget alert email')
param alertEmail string = 'caleb.lucas@generationai.co.nz'

// === LOG ANALYTICS WORKSPACE ===

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'mi-${environmentName}-logs'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// === APPLICATION INSIGHTS ===

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'mi-${environmentName}-insights'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    RetentionInDays: 30
  }
}

// === BUDGET ALERT ===

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'mi-${environmentName}-monthly'
  properties: {
    category: 'Cost'
    amount: 35
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: '2026-02-01'
      endDate: '2027-02-01'
    }
    filter: {
      dimensions: {
        name: 'ResourceGroupName'
        operator: 'In'
        values: [
          resourceGroup().name
        ]
      }
    }
    notifications: {
      warning80: {
        enabled: true
        threshold: 80
        operator: 'GreaterThan'
        contactEmails: [
          alertEmail
        ]
        thresholdType: 'Actual'
      }
      critical100: {
        enabled: true
        threshold: 100
        operator: 'GreaterThan'
        contactEmails: [
          alertEmail
        ]
        thresholdType: 'Actual'
      }
    }
  }
}

// === OUTPUTS ===

output logAnalyticsWorkspaceId string = logAnalytics.id
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output appInsightsInstrumentationKey string = appInsights.properties.InstrumentationKey
