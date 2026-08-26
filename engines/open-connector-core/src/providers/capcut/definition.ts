import type { ProviderDefinition } from "../../core/types.ts";

const service = "capcut";

/**
 * CapCut connector — authenticate with an API key from your CapCut account.
 */
export const provider: ProviderDefinition = {
  service,
  displayName: "CapCut",
  categories: ["Video", "Content Creation"],
  authTypes: ["api_key"],
  auth: [
    {
      type: "api_key",
    },
  ],
  homepageUrl: "https://www.capcut.com",
  actions: [],
};
