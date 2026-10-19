// The web app's container app, deployed with its image by `azd deploy`. The only public endpoint.

param environmentName string
param location string = resourceGroup().location
param name string
param imageName string
param containerAppsEnvironmentName string
param containerRegistryName string
param identityName string
param replayerName string
param webPubSubEndpoint string
param webPubSubHub string
param postgresHost string
param postgresDatabase string

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
  tags: { 'azd-env-name': environmentName, 'azd-service-name': 'web' }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: { external: true, targetPort: 3000, transport: 'http' }
      registries: [{ server: registry.properties.loginServer, identity: identity.id }]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: imageName
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
            { name: 'REPLAYER_URL', value: 'https://${replayerName}.internal.${environment.properties.defaultDomain}' }
            { name: 'WEBPUBSUB_ENDPOINT', value: webPubSubEndpoint }
            { name: 'WEBPUBSUB_HUB', value: webPubSubHub }
            { name: 'POSTGRES_HOST', value: postgresHost }
            { name: 'POSTGRES_DATABASE', value: postgresDatabase }
            { name: 'POSTGRES_USER', value: identity.name }
          ]
          probes: [
            { type: 'Liveness', httpGet: { path: '/api/health', port: 3000 }, periodSeconds: 30 }
            { type: 'Readiness', httpGet: { path: '/api/health', port: 3000 }, periodSeconds: 10 }
          ]
        }
      ]
      // One warm replica, so a judge's first visit doesn't wait for a cold start.
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

output SERVICE_WEB_URL string = 'https://${app.properties.configuration.ingress.fqdn}'
