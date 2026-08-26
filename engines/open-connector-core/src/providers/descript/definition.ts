import type { ProviderDefinition } from "../../core/types.ts";

const service = "descript";

/**
 * Descript connector — authenticate with an API key from your Descript account.
 */
export const provider: ProviderDefinition = {
  service,
  displayName: "Descript",
  categories: ["Video", "Audio"],
  authTypes: ["api_key"],
  auth: [
    {
      type: "api_key",
    },
  ],
  homepageUrl: "https://www.descript.com",
  actions: [],
};
