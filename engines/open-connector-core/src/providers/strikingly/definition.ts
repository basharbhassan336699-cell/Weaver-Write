import type { ProviderDefinition } from "../../core/types.ts";

const service = "strikingly";

/**
 * Strikingly connector — authenticate with an API key from your Strikingly account.
 */
export const provider: ProviderDefinition = {
  service,
  displayName: "Strikingly",
  categories: ["Website Builders"],
  authTypes: ["api_key"],
  auth: [
    {
      type: "api_key",
    },
  ],
  homepageUrl: "https://www.strikingly.com",
  actions: [],
};
