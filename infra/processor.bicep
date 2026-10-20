// The processor's container app, deployed with its image by `azd deploy`. No ingress: it reads the
// feed hub, writes Postgres and pushes to Web PubSub.

param environmentName string
param location string = resourceGroup().location
param name string
param imageName string
param containerAppsEnvironmentName string
param containerRegistryName string
param identityName string
param webIdentityName string
param agentsIdentityName string
param eventHubNamespace string
param eventHubName string
param checkpointBlobUrl string
param checkpointContainer string
param webPubSubEndpoint string
param webPubSubHub string
param postgresHost string
param postgresDatabase string

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: identityName
}

resource webIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: webIdentityName
}

resource agentsIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: agentsIdentityName
}

resource environment 'Microsoft.App/managedEnvironments@2025-07-01' existing = {
  name: containerAppsEnvironmentName
}

resource registry 'Microsoft.ContainerRegistry/registries@2025-04-01' existing = {
  name: containerRegistryName
}

resource app 'Microsoft.App/containerApps@2025-07-01' = {
  name: name
  location: location
  tags: { 'azd-env-name': environmentName, 'azd-service-name': 'processor' }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [{ server: registry.properties.loginServer, identity: identity.id }]
    }
    template: {
      containers: [
        {
          name: 'processor'
          image: imageName
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
            { name: 'EVENTHUB_NAMESPACE', value: eventHubNamespace }
            { name: 'EVENTHUB_NAME', value: eventHubName }
            { name: 'CHECKPOINT_BLOB_URL', value: checkpointBlobUrl }
            { name: 'CHECKPOINT_CONTAINER', value: checkpointContainer }
            { name: 'WEBPUBSUB_ENDPOINT', value: webPubSubEndpoint }
            { name: 'WEBPUBSUB_HUB', value: webPubSubHub }
            { name: 'POSTGRES_HOST', value: postgresHost }
            { name: 'POSTGRES_DATABASE', value: postgresDatabase }
            // The processor signs in to Postgres as its identity, which the server knows by name.
            { name: 'POSTGRES_USER', value: identity.name }
            { name: 'WEB_DB_ROLE', value: webIdentity.name }
            { name: 'WEB_DB_OBJECT_ID', value: webIdentity.properties.principalId }
            { name: 'AGENTS_DB_ROLE', value: agentsIdentity.name }
            { name: 'AGENTS_DB_OBJECT_ID', value: agentsIdentity.properties.principalId }
          ]
        }
      ]
      // One replica holds every run's state; restarts resume from the checkpoint and the stored feed.
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}
