// Everything the services share, in one resource group. Each service runs as its own user-assigned
// identity with only the data-plane roles it needs; no resource accepts keys or passwords.

param location string
param tags object
@description('Suffix that makes resource names unique to the subscription, environment and region')
param token string
param principalId string
param principalType string
param principalName string
param clientIpAddress string
param webPubSubSku string
param translatorEnabled bool
param deployWriterModel bool

var feedHubName = 'feed'
var checkpointContainerName = 'checkpoints'
var webPubSubHubName = 'footnote'
var databaseName = 'footnote'
var foundryProjectName = 'footnote'
// The writers' model. Global Standard bills per token; the capacity caps the rate (thousands of
// tokens a minute), not the bill.
var writerModel = { name: 'gpt-5-mini', version: '2025-08-07', capacity: 100 }

// Built-in role definitions.
var roles = {
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  eventHubsDataSender: '2b629674-e913-4c01-ae53-ef4638d8f975'
  eventHubsDataReceiver: 'a638d3c7-ab3a-418d-83e6-5f17a39d4fde'
  eventHubsDataOwner: 'f526a384-b230-433a-b45c-95f59c4a2dec'
  storageBlobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  webPubSubServiceOwner: '12cf5a90-567b-43ae-8102-96cf46c7d9b4'
  foundryUser: '53ca6127-db72-4b80-b1b0-d745d6d5456d'
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  monitoringMetricsPublisher: '3913510d-42f4-4e42-8a64-420c390055eb'
}

// --- Identities -----------------------------------------------------------------------------------

resource replayerIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: 'id-replayer-${token}'
  location: location
  tags: tags
}

resource processorIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: 'id-processor-${token}'
  location: location
  tags: tags
}

resource webIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: 'id-web-${token}'
  location: location
  tags: tags
}

resource agentsIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: 'id-agents-${token}'
  location: location
  tags: tags
}

// --- Logs -----------------------------------------------------------------------------------------

resource logs 'Microsoft.OperationalInsights/workspaces@2025-02-01' = {
  name: 'log-${token}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    // A ceiling on ingestion cost: the first 5 GB a month are free, and the services log little.
    workspaceCapping: { dailyQuotaGb: json('0.2') }
  }
}

// Traces from the agents service (src/footnote/telemetry.py), kept in the workspace above and under
// its cap. Local auth is off: the agents publish with their managed identity.
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${token}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
    IngestionMode: 'LogAnalytics'
    DisableLocalAuth: true
  }
}

resource agentsPublishTraces 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appInsights.id, agentsIdentity.id, roles.monitoringMetricsPublisher)
  scope: appInsights
  properties: {
    principalId: agentsIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.monitoringMetricsPublisher)
  }
}

resource developerPublishesTraces 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(appInsights.id, principalId, roles.monitoringMetricsPublisher)
  scope: appInsights
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.monitoringMetricsPublisher)
  }
}

// --- Container registry and apps environment ------------------------------------------------------

resource registry 'Microsoft.ContainerRegistry/registries@2025-04-01' = {
  name: 'crfootnote${token}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
    anonymousPullEnabled: false
  }
}

resource replayerPulls 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, replayerIdentity.id, roles.acrPull)
  scope: registry
  properties: {
    principalId: replayerIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
  }
}

resource processorPulls 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, processorIdentity.id, roles.acrPull)
  scope: registry
  properties: {
    principalId: processorIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
  }
}

resource webPulls 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, webIdentity.id, roles.acrPull)
  scope: registry
  properties: {
    principalId: webIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
  }
}

resource agentsPulls 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, agentsIdentity.id, roles.acrPull)
  scope: registry
  properties: {
    principalId: agentsIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
  }
}

// Consumption profile only: billed per second of use, with no fixed environment charge.
resource environment 'Microsoft.App/managedEnvironments@2025-07-01' = {
  name: 'cae-${token}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: { destination: 'azure-monitor' }
    workloadProfiles: [{ name: 'Consumption', workloadProfileType: 'Consumption' }]
    zoneRedundant: false
  }
}

resource environmentLogs 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'logs'
  scope: environment
  properties: {
    workspaceId: logs.id
    logAnalyticsDestinationType: 'Dedicated'
    logs: [{ categoryGroup: 'allLogs', enabled: true }]
  }
}

// --- Event Hubs: the feed -------------------------------------------------------------------------

resource eventHubs 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: 'evhns-footnote-${token}'
  location: location
  tags: tags
  sku: { name: 'Basic', tier: 'Basic', capacity: 1 }
  properties: {
    disableLocalAuth: true
    minimumTlsVersion: '1.2'
    isAutoInflateEnabled: false
  }
}

resource feedHub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: eventHubs
  name: feedHubName
  properties: {
    partitionCount: 2
    messageRetentionInDays: 1
  }
}

resource replayerSends 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(feedHub.id, replayerIdentity.id, roles.eventHubsDataSender)
  scope: feedHub
  properties: {
    principalId: replayerIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.eventHubsDataSender)
  }
}

resource processorReceives 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(feedHub.id, processorIdentity.id, roles.eventHubsDataReceiver)
  scope: feedHub
  properties: {
    principalId: processorIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.eventHubsDataReceiver)
  }
}

resource developerOwnsEventHubs 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(eventHubs.id, principalId, roles.eventHubsDataOwner)
  scope: eventHubs
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.eventHubsDataOwner)
  }
}

// --- Storage: the processor's Event Hubs checkpoints ----------------------------------------------

resource storage 'Microsoft.Storage/storageAccounts@2025-06-01' = {
  name: 'stfootnote${token}'
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2025-06-01' = {
  parent: storage
  name: 'default'
}

resource checkpointContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-06-01' = {
  parent: blobService
  name: checkpointContainerName
  properties: { publicAccess: 'None' }
}

resource processorCheckpoints 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(checkpointContainer.id, processorIdentity.id, roles.storageBlobDataContributor)
  scope: checkpointContainer
  properties: {
    principalId: processorIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataContributor)
  }
}

resource developerCheckpoints 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(checkpointContainer.id, principalId, roles.storageBlobDataContributor)
  scope: checkpointContainer
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataContributor)
  }
}

// --- Web PubSub: pushing to viewers ---------------------------------------------------------------

resource webPubSub 'Microsoft.SignalRService/webPubSub@2024-03-01' = {
  name: 'wps-footnote-${token}'
  location: location
  tags: tags
  sku: { name: webPubSubSku, capacity: 1 }
  properties: {
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

// The processor sends to groups; the web app issues viewers' client tokens.
resource processorPushes 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(webPubSub.id, processorIdentity.id, roles.webPubSubServiceOwner)
  scope: webPubSub
  properties: {
    principalId: processorIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.webPubSubServiceOwner)
  }
}

// The agents push the versions they write.
resource agentsPush 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(webPubSub.id, agentsIdentity.id, roles.webPubSubServiceOwner)
  scope: webPubSub
  properties: {
    principalId: agentsIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.webPubSubServiceOwner)
  }
}

resource webIssuesTokens 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(webPubSub.id, webIdentity.id, roles.webPubSubServiceOwner)
  scope: webPubSub
  properties: {
    principalId: webIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.webPubSubServiceOwner)
  }
}

resource developerOwnsWebPubSub 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(webPubSub.id, principalId, roles.webPubSubServiceOwner)
  scope: webPubSub
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.webPubSubServiceOwner)
  }
}

// --- Postgres: runs, their feed and state ---------------------------------------------------------

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: 'psql-footnote-${token}'
  location: location
  tags: tags
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '17'
    storage: { storageSizeGB: 32, autoGrow: 'Disabled' }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    network: { publicNetworkAccess: 'Enabled' }
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Disabled'
      tenantId: tenant().tenantId
    }
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: databaseName
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

// Container Apps on the Consumption profile have no fixed outbound address, so the firewall admits
// Azure services. Sign-in still needs an Entra token for a role the server knows.
resource allowAzureServices 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

resource allowDeveloper 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = if (!empty(clientIpAddress)) {
  parent: postgres
  name: 'Developer'
  properties: { startIpAddress: clientIpAddress, endIpAddress: clientIpAddress }
}

// The processor owns the schema: it runs the migrations and creates the web app's role.
module processorAdministrator 'modules/postgres-admin.bicep' = {
  name: 'postgres-admin-processor'
  params: {
    serverName: postgres.name
    principalId: processorIdentity.properties.principalId
    principalName: processorIdentity.name
    principalType: 'ServicePrincipal'
  }
  dependsOn: [database, allowAzureServices]
}

// The server applies one administrator change at a time.
module developerAdministrator 'modules/postgres-admin.bicep' = if (!empty(principalId) && !empty(principalName)) {
  name: 'postgres-admin-developer'
  params: {
    serverName: postgres.name
    principalId: principalId
    principalName: principalName
    principalType: principalType
  }
  dependsOn: [processorAdministrator]
}

// --- Foundry: the agents' model --------------------------------------------------------------------

resource foundry 'Microsoft.CognitiveServices/accounts@2026-09-01' = {
  name: 'ai-footnote-${token}'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: 'ai-footnote-${token}'
    allowProjectManagement: true
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2026-09-01' = {
  parent: foundry
  name: foundryProjectName
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'Footnote'
    description: 'The agents that word Footnote match insights'
  }
}

// Its own module, checked once the account exists (modules/model-deployment.bicep says why). Azure
// also refuses to submit it again once it exists, even unchanged, so later provisions leave it out
// (deployWriterModel, set from DEPLOY_WRITER_MODEL).
module writerDeployment 'modules/model-deployment.bicep' = if (deployWriterModel) {
  name: 'writer-model'
  params: {
    accountName: foundry.name
    accountEndpoint: foundry.properties.endpoint
    modelName: writerModel.name
    modelVersion: writerModel.version
    capacity: writerModel.capacity
  }
  // An account takes one change at a time.
  dependsOn: [foundryProject]
}

resource agentsUseFoundry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundryProject.id, agentsIdentity.id, roles.foundryUser)
  scope: foundryProject
  properties: {
    principalId: agentsIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.foundryUser)
  }
}

resource developerUsesFoundry 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(foundryProject.id, principalId, roles.foundryUser)
  scope: foundryProject
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.foundryUser)
  }
}

// The agents' evaluations judge cards through the account's OpenAI endpoint
// (src/footnote/evals/groundedness.py), which a role on the project doesn't reach.
resource developerJudgesWithFoundry 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(foundry.id, principalId, roles.foundryUser)
  scope: foundry
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.foundryUser)
  }
}

// --- Translator: Spanish and French cards (free tier: 2M characters a month) ----------------------

resource translator 'Microsoft.CognitiveServices/accounts@2026-09-01' = if (translatorEnabled) {
  name: 'tr-footnote-${token}'
  location: location
  tags: tags
  kind: 'TextTranslation'
  sku: { name: 'F0' }
  properties: {
    customSubDomainName: 'tr-footnote-${token}'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource agentsTranslate 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (translatorEnabled) {
  name: guid(translator.id, agentsIdentity.id, roles.cognitiveServicesUser)
  scope: translator
  properties: {
    principalId: agentsIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesUser)
  }
}

resource developerTranslates 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (translatorEnabled && !empty(principalId)) {
  name: guid(translator.id, principalId, roles.cognitiveServicesUser)
  scope: translator
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesUser)
  }
}

output registryLoginServer string = registry.properties.loginServer
output registryName string = registry.name
output environmentName string = environment.name
output eventHubNamespace string = '${eventHubs.name}.servicebus.windows.net'
output eventHubName string = feedHub.name
output checkpointBlobUrl string = storage.properties.primaryEndpoints.blob
output checkpointContainer string = checkpointContainer.name
output webPubSubEndpoint string = 'https://${webPubSub.properties.hostName}'
output webPubSubHub string = webPubSubHubName
output postgresHost string = postgres.properties.fullyQualifiedDomainName
output postgresDatabase string = database.name
output replayerName string = 'ca-replayer-${token}'
output replayerIdentityName string = replayerIdentity.name
output processorName string = 'ca-processor-${token}'
output processorIdentityName string = processorIdentity.name
output webName string = 'ca-web-${token}'
output webIdentityName string = webIdentity.name
output agentsName string = 'ca-agents-${token}'
output agentsIdentityName string = agentsIdentity.name
output foundryProjectEndpoint string = 'https://${foundry.properties.customSubDomainName}.services.ai.azure.com/api/projects/${foundryProject.name}'
output foundryModel string = deployWriterModel ? writerDeployment!.outputs.name : writerModel.name
// Where the agents send traces. It names the resource and its ingestion endpoint; with local auth off,
// sending also takes an Entra token for a role on the resource.
output applicationInsightsConnectionString string = appInsights.properties.ConnectionString
// The resource's own subdomain, where Microsoft Entra tokens work: for a Translator,
// properties.endpoint names the global endpoint, which wants a key or extra headers.
output translatorEndpoint string = translatorEnabled ? translator!.properties.endpoints.TextTranslation : ''
