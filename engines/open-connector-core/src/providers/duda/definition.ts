import type { ProviderDefinition } from "../../core/types.ts";

const service = "duda";

/**
 * Duda connector — authenticate with an API key from your Duda account.
 */
export const provider: ProviderDefinition = {
  service,
  displayName: "Duda",
  categories: ["Website Builders"],
  authTypes: ["api_key"],
  auth: [
    {
      type: "api_key",
    },
  ],
  homepageUrl: "https://www.duda.co",
  actions: [],
};
