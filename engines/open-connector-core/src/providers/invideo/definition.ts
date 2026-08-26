import type { ProviderDefinition } from "../../core/types.ts";

const service = "invideo";

/**
 * InVideo connector — authenticate with an API key from your InVideo account.
 */
export const provider: ProviderDefinition = {
  service,
  displayName: "InVideo",
  categories: ["Video", "AI"],
  authTypes: ["api_key"],
  auth: [
    {
      type: "api_key",
    },
  ],
  homepageUrl: "https://invideo.io",
  actions: [],
};
