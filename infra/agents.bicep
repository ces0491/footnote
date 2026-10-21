// The agents service's container app, deployed with its image by `azd deploy`. It claims jobs from
// Postgres, serves the match tools to its own writers on localhost, calls the Foundry model and
// pushes the versions it writes to Web PubSub. Its only ingress is internal: the producer's desk,
// which the web app's console calls from inside the Container Apps environment.

param environmentName string
param location string = resourceGroup().location
param name string
param imageName string
param containerAppsEnvironmentName string
param containerRegistryName string
param identityName string
param webPubSubEndpoint string
param webPubSubHub string
param postgresHost string
param postgresDatabase string
param foundryProjectEndpoint string
param foundryModel string

@description('Azure AI Translator for the Spanish and French cards; empty leaves them in English')
param translatorEndpoint string = ''

@description('Application Insights for the agents\' traces; empty sends none')
param applicationInsightsConnectionString string = ''

@description('Agent runs a day (UTC) before every job keeps its template: a ceiling on what the model can cost')
param agentDailyRuns int = 150

@description('Seconds from a job being claimed to its draft before the template stands: room for one revision')
param agentDeadlineSeconds int = 45

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
  tags: { 'azd-env-name': environmentName, 'azd-service-name': 'agents' }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: { external: false, targetPort: 8080, transport: 'http' }
      registries: [{ server: registry.properties.loginServer, identity: identity.id }]
    }
    template: {
      containers: [
        {
          name: 'agents'
          image: imageName
          // The match tools fold a run's feed with the models, as the processor does, so the
          // service needs the processor's memory and more for the agent framework.
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
            { name: 'FOUNDRY_MODEL', value: foundryModel }
            { name: 'WEBPUBSUB_ENDPOINT', value: webPubSubEndpoint }
            { name: 'WEBPUBSUB_HUB', value: webPubSubHub }
            { name: 'POSTGRES_HOST', value: postgresHost }
            { name: 'POSTGRES_DATABASE', value: postgresDatabase }
            // The processor creates this role at start-up and grants it what the agents write.
            { name: 'POSTGRES_USER', value: identity.name }
            { name: 'AGENT_DAILY_RUNS', value: string(agentDailyRuns) }
            { name: 'AGENT_DEADLINE_SECONDS', value: string(agentDeadlineSeconds) }
            { name: 'DESK_PORT', value: '8080' }
            { name: 'TRANSLATOR_ENDPOINT', value: translatorEndpoint }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: applicationInsightsConnectionString }
          ]
        }
      ]
      // One replica: the cache and the daily count are in Postgres, so more would be safe, but one
      // is enough for demo traffic.
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}
