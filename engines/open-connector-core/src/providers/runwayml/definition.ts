import type { ProviderDefinition } from "../../core/types.ts";

const service = "runwayml";

/**
 * Runway connector — authenticate with an API key from your Runway account.
 */
export const provider: ProviderDefinition = {
  service,
  displayName: "Runway",
  categories: ["Video", "AI"],
  authTypes: ["api_key"],
  auth: [
    {
      type: "api_key",
    },
  ],
  homepageUrl: "https://runwayml.com",
  actions: [],
};
