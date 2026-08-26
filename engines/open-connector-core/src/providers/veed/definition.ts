import type { ProviderDefinition } from "../../core/types.ts";

const service = "veed";

/**
 * VEED connector — authenticate with an API key from your VEED account.
 */
export const provider: ProviderDefinition = {
  service,
  displayName: "VEED",
  categories: ["Video", "Content Creation"],
  authTypes: ["api_key"],
  auth: [
    {
      type: "api_key",
    },
  ],
  homepageUrl: "https://www.veed.io",
  actions: [],
};
