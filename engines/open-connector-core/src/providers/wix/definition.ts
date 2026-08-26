import type { ProviderDefinition } from "../../core/types.ts";

const service = "wix";

/**
 * Wix connector — authenticate with an API key from your Wix account.
 */
export const provider: ProviderDefinition = {
  service,
  displayName: "Wix",
  categories: ["Website Builders", "Productivity"],
  authTypes: ["api_key"],
  auth: [
    {
      type: "api_key",
    },
  ],
  homepageUrl: "https://www.wix.com",
  actions: [],
};
