import type { ProviderDefinition } from "../../core/types.ts";

const service = "weebly";

/**
 * Weebly connector — authenticate with an API key from your Weebly account.
 */
export const provider: ProviderDefinition = {
  service,
  displayName: "Weebly",
  categories: ["Website Builders"],
  authTypes: ["api_key"],
  auth: [
    {
      type: "api_key",
    },
  ],
  homepageUrl: "https://www.weebly.com",
  actions: [],
};
