import type { ProviderDefinition } from "../../core/types.ts";

const service = "pictory";

/**
 * Pictory connector — authenticate with an API key from your Pictory account.
 */
export const provider: ProviderDefinition = {
  service,
  displayName: "Pictory",
  categories: ["Video", "AI"],
  authTypes: ["api_key"],
  auth: [
    {
      type: "api_key",
    },
  ],
  homepageUrl: "https://pictory.ai",
  actions: [],
};
