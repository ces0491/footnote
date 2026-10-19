import "server-only";

import { AzureCliCredential, ManagedIdentityCredential, type TokenCredential } from "@azure/identity";

let cached: TokenCredential | undefined;

// In Azure the app runs as its user-assigned managed identity (AZURE_CLIENT_ID). Locally it uses the
// developer's Azure CLI sign-in, which `azd provision` grants the same roles.
export function credential(): TokenCredential {
  if (!cached) {
    const clientId = process.env.AZURE_CLIENT_ID;
    cached = clientId ? new ManagedIdentityCredential({ clientId }) : new AzureCliCredential();
  }
  return cached;
}

export async function accessToken(scope: string): Promise<string> {
  const token = await credential().getToken(scope);
  if (!token) throw new Error(`no access token for ${scope}`);
  return token.token;
}
