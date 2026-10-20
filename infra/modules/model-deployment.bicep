// A model deployment on a Foundry account, as its own nested deployment.
//
// Azure's checks refuse a model deployment validated in the same request as its account (error
// 715-123420, "unusual activity"). Taking a value that exists only once the account does
// (`accountEndpoint`) makes Azure check this deployment when it runs, after the account is there.

param accountName string

@description('The account\'s endpoint, passed so this deployment is checked after the account exists')
param accountEndpoint string

param modelName string
param modelVersion string

@description('Thousands of tokens a minute. Global Standard bills per token; this caps the rate, not the bill')
param capacity int

resource account 'Microsoft.CognitiveServices/accounts@2026-09-01' existing = {
  name: accountName
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2026-09-01' = {
  parent: account
  name: modelName
  sku: { name: 'GlobalStandard', capacity: capacity }
  properties: {
    model: { format: 'OpenAI', name: modelName, version: modelVersion }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

output name string = deployment.name
output accountEndpoint string = accountEndpoint
