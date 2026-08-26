import type { ProviderDefinition } from "../../core/types.ts";

const service = "squarespace";

/**
 * Squarespace connector — authenticate with an API key from your Squarespace account.
 */
export const provider: ProviderDefinition = {
  service,
  displayName: "Squarespace",
  categories: ["Website Builders", "Marketing"],
  authTypes: ["api_key"],
  auth: [
    {
      type: "api_key",
    },
  ],
  homepageUrl: "https://www.squarespace.com",
  actions: [],
};
