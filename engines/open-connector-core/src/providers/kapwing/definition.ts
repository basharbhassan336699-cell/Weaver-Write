import type { ProviderDefinition } from "../../core/types.ts";

const service = "kapwing";

/**
 * Kapwing connector — authenticate with an API key from your Kapwing account.
 */
export const provider: ProviderDefinition = {
  service,
  displayName: "Kapwing",
  categories: ["Video", "Content Creation"],
  authTypes: ["api_key"],
  auth: [
    {
      type: "api_key",
    },
  ],
  homepageUrl: "https://www.kapwing.com",
  actions: [],
};
