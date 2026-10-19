// Footnote's Azure resources: the resource group and everything the services share. The container
// apps themselves are deployed with their images by `azd deploy` from infra/<service>.bicep.
targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the azd environment, used in resource names and tags')
param environmentName string

@minLength(1)
@description('Region for every resource')
param location string

@description('Object ID of whoever runs azd, granted data-plane roles for local development. Empty to skip.')
param principalId string = ''

@allowed(['User', 'ServicePrincipal'])
param principalType string = 'User'

@description('User principal name of that person, made a Postgres Entra administrator when set')
param principalName string = ''

@description('Public IP allowed through the Postgres firewall for local development, or empty')
param clientIpAddress string = ''

@allowed(['Free_F1', 'Standard_S1'])
@description('Web PubSub tier. Free allows 20 connections and 20,000 messages a day; changing tier costs 30-60 minutes of downtime')
param webPubSubSku string = 'Free_F1'

var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  name: 'resources'
  scope: rg
  params: {
    location: location
    tags: tags
    token: uniqueString(subscription().id, environmentName, location)
    principalId: principalId
    principalType: principalType
    principalName: principalName
    clientIpAddress: clientIpAddress
    webPubSubSku: webPubSubSku
  }
}

output AZURE_LOCATION string = location
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.registryLoginServer
output AZURE_CONTAINER_REGISTRY_NAME string = resources.outputs.registryName
output AZURE_CONTAINER_ENVIRONMENT_NAME string = resources.outputs.environmentName
output EVENTHUB_NAMESPACE string = resources.outputs.eventHubNamespace
output EVENTHUB_NAME string = resources.outputs.eventHubName
output CHECKPOINT_BLOB_URL string = resources.outputs.checkpointBlobUrl
output CHECKPOINT_CONTAINER string = resources.outputs.checkpointContainer
output WEBPUBSUB_ENDPOINT string = resources.outputs.webPubSubEndpoint
output WEBPUBSUB_HUB string = resources.outputs.webPubSubHub
output POSTGRES_HOST string = resources.outputs.postgresHost
output POSTGRES_DATABASE string = resources.outputs.postgresDatabase
output SERVICE_REPLAYER_NAME string = resources.outputs.replayerName
output SERVICE_REPLAYER_IDENTITY_NAME string = resources.outputs.replayerIdentityName
output SERVICE_PROCESSOR_NAME string = resources.outputs.processorName
output SERVICE_PROCESSOR_IDENTITY_NAME string = resources.outputs.processorIdentityName
output SERVICE_WEB_NAME string = resources.outputs.webName
output SERVICE_WEB_IDENTITY_NAME string = resources.outputs.webIdentityName
