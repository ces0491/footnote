import "server-only";

import { z } from "zod";

// Set by infra/web.bicep in Azure. Locally, copy them from `azd env get-values` (see the README).
const schema = z.object({
  REPLAYER_URL: z.url(),
  WEBPUBSUB_ENDPOINT: z.url(),
  WEBPUBSUB_HUB: z.string().min(1),
  POSTGRES_HOST: z.string().min(1),
  POSTGRES_DATABASE: z.string().min(1),
  // The Entra role the web app signs in as: its managed identity's name, or the developer's UPN.
  POSTGRES_USER: z.string().min(1),
});

export type ServerEnv = z.infer<typeof schema>;

let cached: ServerEnv | undefined;

// Read on first use rather than at import, so `next build` doesn't need the deployment's settings.
export function serverEnv(): ServerEnv {
  cached ??= schema.parse(process.env);
  return cached;
}
