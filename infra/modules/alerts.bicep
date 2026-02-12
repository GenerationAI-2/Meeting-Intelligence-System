// alerts.bicep — Azure Monitor alert rules for Meeting Intelligence
// Part of Meeting Intelligence IaC (D16 3.2)
//
// Creates metric alerts for Container App health + a log alert for auth failure spikes.
// Sends notifications via email action group.

@description('Environment name')
param environmentName string

@description('Azure region')
param location string

@description('Resource tags')
param tags object

@description('Container App resource ID')
param containerAppId string

@description('Log Analytics workspace resource ID')
param logAnalyticsWorkspaceId string

@description('Minimum replicas — replica-zero alert only enabled when > 0')
param minReplicas int

@description('Alert notification email')
param alertEmail string = 'caleb.lucas@generationai.co.nz'

// === ACTION GROUP ===

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'mi-${environmentName}-alerts'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'mi-alerts'
    enabled: true
    emailReceivers: [
      {
        name: 'Admin'
        emailAddress: alertEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

// === METRIC ALERTS ===

// 1. 5xx error rate — severity 1 (Error)
resource alert5xx 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'mi-${environmentName}-5xx-errors'
  location: 'global'
  tags: tags
  properties: {
    description: '5xx server errors exceeded threshold (>5 in 5 minutes)'
    severity: 1
    enabled: true
    scopes: [containerAppId]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: '5xxErrors'
          metricName: 'Requests'
          metricNamespace: 'Microsoft.App/containerApps'
          operator: 'GreaterThan'
          threshold: 5
          timeAggregation: 'Total'
          dimensions: [
            {
              name: 'statusCodeCategory'
              operator: 'Include'
              values: ['5xx']
            }
          ]
        }
      ]
    }
    actions: [{ actionGroupId: actionGroup.id }]
  }
}

// 2. Response time — severity 2 (Warning)
resource alertResponseTime 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'mi-${environmentName}-response-time'
  location: 'global'
  tags: tags
  properties: {
    description: 'Average response time exceeds 5 seconds'
    severity: 2
    enabled: true
    scopes: [containerAppId]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'HighResponseTime'
          metricName: 'ResponseTime'
          metricNamespace: 'Microsoft.App/containerApps'
          operator: 'GreaterThan'
          threshold: 5000
          timeAggregation: 'Average'
        }
      ]
    }
    actions: [{ actionGroupId: actionGroup.id }]
  }
}

// 3. Excessive restarts — severity 2 (Warning)
resource alertRestarts 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'mi-${environmentName}-restarts'
  location: 'global'
  tags: tags
  properties: {
    description: 'Container restarted more than 3 times in 5 minutes'
    severity: 2
    enabled: true
    scopes: [containerAppId]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'RestartCount'
          metricName: 'RestartCount'
          metricNamespace: 'Microsoft.App/containerApps'
          operator: 'GreaterThan'
          threshold: 3
          timeAggregation: 'Maximum'
        }
      ]
    }
    actions: [{ actionGroupId: actionGroup.id }]
  }
}

// 4. Replica count zero — severity 1 (Error)
// Only enabled for environments with minReplicas > 0 (e.g. Marshall).
// For team/demo, scale-to-zero is expected behaviour.
resource alertReplicaZero 'Microsoft.Insights/metricAlerts@2018-03-01' = if (minReplicas > 0) {
  name: 'mi-${environmentName}-replica-zero'
  location: 'global'
  tags: tags
  properties: {
    description: 'No active replicas — app is down'
    severity: 1
    enabled: true
    scopes: [containerAppId]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'ReplicaCount'
          metricName: 'Replicas'
          metricNamespace: 'Microsoft.App/containerApps'
          operator: 'LessThan'
          threshold: 1
          timeAggregation: 'Maximum'
        }
      ]
    }
    actions: [{ actionGroupId: actionGroup.id }]
  }
}

// 5. High CPU — severity 2 (Warning)
resource alertCpu 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'mi-${environmentName}-high-cpu'
  location: 'global'
  tags: tags
  properties: {
    description: 'CPU usage exceeds 90% of allocated cores'
    severity: 2
    enabled: true
    scopes: [containerAppId]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'HighCpu'
          metricName: 'UsageNanoCores'
          metricNamespace: 'Microsoft.App/containerApps'
          operator: 'GreaterThan'
          threshold: 225000000 // 90% of 0.25 CPU = 0.225 cores
          timeAggregation: 'Average'
        }
      ]
    }
    actions: [{ actionGroupId: actionGroup.id }]
  }
}

// 6. High memory — severity 2 (Warning)
resource alertMemory 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'mi-${environmentName}-high-memory'
  location: 'global'
  tags: tags
  properties: {
    description: 'Memory usage exceeds 90% of allocated memory'
    severity: 2
    enabled: true
    scopes: [containerAppId]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'HighMemory'
          metricName: 'WorkingSetBytes'
          metricNamespace: 'Microsoft.App/containerApps'
          operator: 'GreaterThan'
          threshold: 483000000 // 90% of 0.5Gi (~536MB)
          timeAggregation: 'Average'
        }
      ]
    }
    actions: [{ actionGroupId: actionGroup.id }]
  }
}

// === LOG-BASED ALERT ===

// 7. Auth failure spike — severity 1 (Error)
// Detects potential brute force: >20 401 responses in 5 minutes.
resource alertAuthFailure 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = {
  name: 'mi-${environmentName}-auth-failure-spike'
  location: location
  tags: tags
  kind: 'LogAlert'
  properties: {
    displayName: 'Auth Failure Spike - ${environmentName}'
    description: 'Potential brute force: >20 401 responses in 5 minutes'
    enabled: true
    severity: 1
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    scopes: [logAnalyticsWorkspaceId]
    autoMitigate: true
    criteria: {
      allOf: [
        {
          query: '''
            ContainerAppConsoleLogs_CL
            | where Log_s has "401" or Log_s has "Unauthorized"
            | summarize Count401 = count() by bin(TimeGenerated, 5m)
          '''
          operator: 'GreaterThan'
          threshold: 20
          timeAggregation: 'Count'
          failingPeriods: {
            minFailingPeriodsToAlert: 1
            numberOfEvaluationPeriods: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [actionGroup.id]
    }
  }
}
