import type { CredentialValidators, ProviderExecutors } from "../../core/types.ts";

import { optionalString, requiredString } from "../../core/cast.ts";
import { defineProviderExecutors, requireOAuthCredential } from "../provider-runtime.ts";
import {
  baiduNetdiskActionHandlers,
  fetchBaiduNetdiskAccount,
  requireBaiduNetdiskAppDirectoryPath,
} from "./runtime.ts";

export const executors: ProviderExecutors = defineProviderExecutors({
  service: "baidu_netdisk",
  handlers: baiduNetdiskActionHandlers,
  async createContext(context, fetcher) {
    const credential = await requireOAuthCredential(context, "baidu_netdisk");
    const oauthClientExtra = credential.metadata.oauthClientExtra;
    return {
      accessToken: credential.accessToken,
      appDirectoryPath: requireBaiduNetdiskAppDirectoryPath(
        typeof oauthClientExtra === "object" && oauthClientExtra !== null
          ? (oauthClientExtra as Record<string, unknown>).appDirectoryPath
          : undefined,
      ),
      fetcher,
      signal: context.signal,
    };
  },
});

export const credentialValidators: CredentialValidators = {
  async oauth2(input, { fetcher }) {
    const account = await fetchBaiduNetdiskAccount(input.accessToken, fetcher);
    return {
      profile: {
        accountId: requiredString(account.accountId, "baidu_netdisk account id"),
        displayName: optionalString(account.accountLabel) ?? account.accountId,
      },
      metadata: account.providerMetadata,
    };
  },
};
