import "server-only";

import { WebPubSubServiceClient } from "@azure/web-pubsub";

import { groupName } from "@/lib/live/contract";

import { credential } from "./azure";
import { serverEnv } from "./env";

let client: WebPubSubServiceClient | undefined;

function webPubSub(): WebPubSubServiceClient {
  if (!client) {
    const env = serverEnv();
    client = new WebPubSubServiceClient(env.WEBPUBSUB_ENDPOINT, credential(), env.WEBPUBSUB_HUB);
  }
  return client;
}

// A client URL that joins the run's group on connect. The viewer can receive but not join other
// groups or publish: the token carries no roles.
export async function clientUrl(runId: string): Promise<string> {
  const token = await webPubSub().getClientAccessToken({
    groups: [groupName(runId)],
    expirationTimeInMinutes: 60,
  });
  return token.url;
}
