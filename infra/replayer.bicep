// The replayer's container app, deployed with its image by `azd deploy`. Internal ingress only: the
// web app starts and stops replays; nothing outside the environment can reach it.

param environmentName string
param location string = resourceGroup().location
param name string
param imageName string
param containerAppsEnvironmentName string
param containerRegistryName string
param identityName string
param eventHubNamespace string
param eventHubName string

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: identityName
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
  tags: { 'azd-env-name': environmentName, 'azd-service-name': 'replayer' }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: { external: false, targetPort: 8000, transport: 'http' }
      registries: [{ server: registry.properties.loginServer, identity: identity.id }]
    }
    template: {
      containers: [
        {
          name: 'replayer'
          image: imageName
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
            { name: 'EVENTHUB_NAMESPACE', value: eventHubNamespace }
            { name: 'EVENTHUB_NAME', value: eventHubName }
          ]
          probes: [
            { type: 'Liveness', httpGet: { path: '/healthz', port: 8000 }, periodSeconds: 30 }
            { type: 'Readiness', httpGet: { path: '/healthz', port: 8000 }, periodSeconds: 10 }
          ]
        }
      ]
      // Runs live in this replica's memory, so there is exactly one.
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

output SERVICE_REPLAYER_URL string = 'https://${app.properties.configuration.ingress.fqdn}'
