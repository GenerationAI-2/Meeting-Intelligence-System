// =============================================================================
// CAF Naming Template — Copy and customise for new client deployments
// =============================================================================
//
// This template uses Microsoft CAF (Cloud Adoption Framework) naming convention.
// Resource names are derived automatically from environmentName + environmentType:
//
//   Resource Group:          rg-app-<envType>-mi-<client>
//   Container App:           ca-mi-<envType>-<client>
//   Container App Env:       cae-mi-<envType>-<client>
//   SQL Server:              sql-mi-<envType>-<client>
//   SQL Database (general):  sqldb-mi-<envType>-<client>
//   SQL Database (control):  sqldb-mi-<envType>-<client>-control
//   Key Vault:               kv-mi-<envType>-<client>   (max 24 chars — client name <= 10 chars)
//   Log Analytics:           log-mi-<envType>-<client>
//   Application Insights:    appi-mi-<envType>-<client>
//   Action Group:            ag-mi-<envType>-<client>
//
// Usage:
//   1. Copy this file to infra/parameters/<client-name>.bicepparam
//   2. Replace all <PLACEHOLDER> values
//   3. Run: ./infra/deploy-new-client.sh <client-name>
//
// See: https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-naming

using '../main.bicep'

// --- CAF naming (REQUIRED for new deployments) ---
param cafNaming = true
param environmentType = 'prod'

// --- Client identity ---
param environmentName = '<CLIENT_NAME>'        // e.g., 'acme-corp' (max 10 chars for KV compat)
param location = 'newzealandnorth'
param acrName = 'meetingintelacr20260116'

// --- SQL admin ---
param sqlAdminObjectId = '<SQL_ADMIN_OBJECT_ID>'    // Azure AD Object ID for SQL admin
param sqlAdminDisplayName = '<SQL_ADMIN_NAME>'       // e.g., 'Caleb Lucas'

// --- Azure AD auth ---
param azureTenantId = '<AZURE_TENANT_ID>'            // e.g., '12e7fcaa-f776-4545-aacf-e89be7737cf3'
param azureClientId = '<APP_REGISTRATION_CLIENT_ID>' // App Registration Application (Client) ID

// --- Access control ---
param allowedUsers = '<EMAIL_1>,<EMAIL_2>'           // Comma-separated emails for web UI access
param corsOrigins = 'https://placeholder'            // Updated automatically by deploy-new-client.sh Phase 4
param minReplicas = 1                                // 1 for client-facing, 0 for internal
// param faviconPath = '/app/favicons/<CLIENT_NAME>.png'  // Per-client favicon (add PNG to favicons/ dir)

// --- Dynamic params (passed via environment variables at deploy time) ---
param containerImageTag = readEnvironmentVariable('CONTAINER_IMAGE_TAG', 'latest')
param appInsightsConnection = readEnvironmentVariable('APPLICATIONINSIGHTS_CONNECTION_STRING', '')
