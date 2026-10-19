// A Microsoft Entra administrator of a Postgres flexible server. A module because the resource's name
// is the principal's object ID, which for a new identity is known only once the deployment runs.

param serverName string
param principalId string
param principalName string
@allowed(['User', 'ServicePrincipal', 'Group'])
param principalType string

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' existing = {
  name: serverName
}

resource administrator 'Microsoft.DBforPostgreSQL/flexibleServers/administrators@2024-08-01' = {
  parent: server
  name: principalId
  properties: {
    principalName: principalName
    principalType: principalType
    tenantId: tenant().tenantId
  }
}
