import type { ProviderDefinition } from "../../core/types.ts";

const service = "synthesia";

/**
 * Synthesia connector — authenticate with an API key from your Synthesia account.
 */
export const provider: ProviderDefinition = {
  service,
  displayName: "Synthesia",
  categories: ["Video", "AI"],
  authTypes: ["api_key"],
  auth: [
    {
      type: "api_key",
    },
  ],
  homepageUrl: "https://www.synthesia.io",
  actions: [],
};
