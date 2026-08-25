import type { ProviderActionDefinition } from "../../core/provider-definition.ts";

import { s } from "../../core/json-schema.ts";
import { defineProviderAction } from "../../core/provider-definition.ts";

export const baiduNetdiskConnectorScopes = {
  accountRead: "baidu_netdisk.account.read",
  filesRead: "baidu_netdisk.files.read",
  filesWrite: "baidu_netdisk.files.write",
  filesDelete: "baidu_netdisk.files.delete",
} as const;

export const baiduNetdiskProviderScopes = {
  basic: "basic",
  netdisk: "netdisk",
} as const;

export const baiduNetdiskFileCategories = [
  "video",
  "audio",
  "image",
  "document",
  "application",
  "other",
  "torrent",
] as const;

export const baiduNetdiskSemanticMatchSources = [
  "filename",
  "image_ocr",
  "document_text",
  "document_semantic",
  "video_semantic",
  "audio_semantic",
  "image_semantic",
  "card",
] as const;

const userPath = (description: string, _allowRoot = true) => s.nonEmptyString(description);
const fileIdSchema = s.nonEmptyString("A Baidu Netdisk fs_id represented as an unsigned decimal string.");
const cursorSchema = s.nonEmptyString("The decimal Baidu Netdisk start cursor returned by a previous list call.");
const itemNameSchema = s.nonEmptyString("A single file or folder name without path separators.");
const publicFileUrlSchema = s.url(
  "A public HTTP or HTTPS URL whose bytes should be uploaded. For local files, use oo file upload and pass its downloadUrl.",
);
const extensionSchema = s.nonEmptyString("A file extension without a leading dot, such as pdf or docx.");

const nullableString = (description: string) => s.nullable(s.string(description));
const nullableInteger = (description: string) => s.nullable(s.integer(description));

const fileProperties = {
  id: s.string("The lossless Baidu Netdisk fs_id decimal string."),
  name: s.string("The file or folder name."),
  path: s.string("The app-directory-relative path beginning with a slash."),
  kind: s.stringEnum("Whether this item is a file or folder.", ["file", "folder"]),
  category: s.nullable(
    s.stringEnum("The Baidu Netdisk file category, or null for folders.", [...baiduNetdiskFileCategories]),
  ),
  sizeBytes: nullableInteger("The file size in bytes, or null for folders or missing values."),
  createdAt: s.nullable(s.dateTime("The server creation time in ISO 8601 UTC format.")),
  modifiedAt: s.nullable(s.dateTime("The server modification time in ISO 8601 UTC format.")),
  cloudMd5: nullableString("The provider cloud hash, or null when unavailable."),
};
const fileSchema = s.object("A normalized Baidu Netdisk file or folder.", fileProperties);

const uploadedFileSchema = s.object("A normalized file uploaded to Baidu Netdisk.", {
  ...fileProperties,
  id: nullableString(
    "The lossless Baidu Netdisk fs_id decimal string, or null when instant upload succeeds without returning fs_id.",
  ),
});

const semanticFileSchema = s.object("A normalized Baidu Netdisk semantic search match.", {
  ...fileProperties,
  matchSource: s.nullable(
    s.stringEnum("The official Baidu recall source for this match, or null when unavailable.", [
      ...baiduNetdiskSemanticMatchSources,
    ]),
  ),
  matchedContent: nullableString("The matched document, audio, or video text passage, or null when unavailable."),
  ocrText: nullableString("The matched image OCR text, or null when unavailable."),
  passageId: nullableString("The lossless Baidu semantic passage pid decimal string, or null when unavailable."),
});

const emptyInputSchema = s.object("No input is required.", {});
const conflictStrategySchema = s.withDefault(
  s.stringEnum("How Baidu Netdisk should handle a destination name conflict.", ["fail", "rename", "overwrite", "skip"]),
  "fail",
);
const managementOutputSchema = s.object("The result of one synchronous file operation.", {
  sourcePath: s.string("The source app-relative path supplied by the caller."),
  path: nullableString("The app-relative path reported by Baidu, or null when unavailable."),
});

const listInputSchema = s.object(
  "Input for listing files in the Baidu Netdisk app directory.",
  {
    path: s.optional(s.withDefault(userPath("The app-relative directory path to list."), "/")),
    recursive: s.optional(s.withDefault(s.boolean("Whether to recursively list descendants."), false)),
    limit: s.optional(
      s.withDefault(s.integer("The maximum number of items to return.", { minimum: 1, maximum: 1000 }), 1000),
    ),
    sortBy: s.optional(
      s.stringEnum("The field used to sort the complete directory listing.", ["name", "modifiedTime", "size"]),
    ),
    sortOrder: s.optional(s.stringEnum("The directory listing sort direction.", ["ascending", "descending"])),
    cursor: s.optional(cursorSchema),
    categories: s.optional(
      s.array(
        "The file categories to include. Category-filtered results contain files, not folders.",
        s.stringEnum("A Baidu Netdisk file category.", [...baiduNetdiskFileCategories]),
        { minItems: 1, maxItems: baiduNetdiskFileCategories.length },
      ),
    ),
    extensions: s.optional(
      s.array("The file extensions to include within the selected categories.", extensionSchema, { minItems: 1 }),
    ),
    createdAfter: s.optional(s.dateTime("Only include files uploaded strictly after this ISO 8601 timestamp.")),
    modifiedAfter: s.optional(s.dateTime("Only include files modified strictly after this ISO 8601 timestamp.")),
  },
  {
    optional: [
      "path",
      "recursive",
      "limit",
      "sortBy",
      "sortOrder",
      "cursor",
      "categories",
      "extensions",
      "createdAfter",
      "modifiedAfter",
    ],
  },
);

const searchInputSchema = s.object(
  "Input for one bounded Baidu Netdisk keyword search.",
  {
    query: s.nonEmptyString("The keyword to search for, up to 30 UTF-8 characters.", {
      maxLength: 30,
    }),
    path: s.optional(s.withDefault(userPath("The app-relative directory path to search."), "/")),
    recursive: s.optional(s.withDefault(s.boolean("Whether to recursively search descendants."), false)),
    category: s.optional(
      s.stringEnum("The optional Baidu Netdisk file category filter.", [...baiduNetdiskFileCategories]),
    ),
  },
  { optional: ["path", "recursive", "category"] },
);

const semanticSearchInputSchema = s.object(
  "Input for one bounded Baidu Netdisk natural-language semantic search.",
  {
    query: s.nonWhitespaceString("The natural-language description of the files to find."),
    path: s.optional(s.withDefault(userPath("The app-relative directory path to search."), "/")),
    limit: s.optional(
      s.withDefault(
        s.integer("The maximum number of semantic matches to return.", {
          minimum: 1,
          maximum: 500,
        }),
        500,
      ),
    ),
  },
  { optional: ["path", "limit"] },
);

const uploadConflictStrategySchema = s.withDefault(
  s.stringEnum("How Baidu Netdisk should handle an existing destination path.", ["fail", "rename", "overwrite"]),
  "fail",
);

const relocateInputSchema = (operation: string) =>
  s.object(
    `Input for ${operation}ing one Baidu Netdisk file or folder.`,
    {
      sourcePath: userPath("The app-relative source path.", false),
      destinationDirectoryPath: userPath("The app-relative destination directory path."),
      newName: s.optional(itemNameSchema),
      conflictStrategy: s.optional(conflictStrategySchema),
    },
    { optional: ["newName", "conflictStrategy"] },
  );

export const baiduNetdiskActions: ProviderActionDefinition[] = [
  defineProviderAction("baidu_netdisk", {
    name: "get_current_account",
    description: "Get the current Baidu Netdisk account and membership summary.",
    requiredScopes: [baiduNetdiskConnectorScopes.accountRead],
    providerPermissions: [baiduNetdiskProviderScopes.basic, baiduNetdiskProviderScopes.netdisk],
    inputSchema: emptyInputSchema,
    outputSchema: s.object("The current Baidu Netdisk account.", {
      accountId: s.string("The lossless Baidu Netdisk uk decimal string."),
      accountLabel: s.string("The best available Baidu Netdisk account name."),
      avatarUrl: nullableString("The current account avatar URL, or null when unavailable."),
      membership: s.nullable(s.stringEnum("The current Baidu Netdisk membership tier.", ["free", "vip", "svip"])),
    }),
  }),
  defineProviderAction("baidu_netdisk", {
    name: "get_quota",
    description: "Get total, used, remaining, free, and expiring Baidu Netdisk capacity.",
    requiredScopes: [baiduNetdiskConnectorScopes.accountRead],
    providerPermissions: [baiduNetdiskProviderScopes.basic, baiduNetdiskProviderScopes.netdisk],
    inputSchema: emptyInputSchema,
    outputSchema: s.object("The current Baidu Netdisk capacity summary.", {
      totalBytes: s.integer("The total storage capacity in bytes."),
      usedBytes: s.integer("The used storage capacity in bytes."),
      remainingBytes: s.integer("The non-negative remaining storage capacity in bytes."),
      freeQuotaBytes: s.integer("The free storage capacity in bytes."),
      expiresWithinSevenDays: s.boolean("Whether some capacity expires within seven days."),
    }),
  }),
  defineProviderAction("baidu_netdisk", {
    name: "list_files",
    description: "List files and folders within the configured Baidu Netdisk app directory.",
    requiredScopes: [baiduNetdiskConnectorScopes.filesRead],
    providerPermissions: [baiduNetdiskProviderScopes.netdisk],
    inputSchema: listInputSchema,
    outputSchema: s.object("A page of normalized Baidu Netdisk files and folders.", {
      items: s.array("The normalized files and folders in this page.", fileSchema),
      nextCursor: nullableString("The decimal cursor for the next page, or null when complete."),
    }),
  }),
  defineProviderAction("baidu_netdisk", {
    name: "get_file_metadata",
    description: "Get normalized metadata for up to 100 Baidu Netdisk file IDs.",
    requiredScopes: [baiduNetdiskConnectorScopes.filesRead],
    providerPermissions: [baiduNetdiskProviderScopes.netdisk],
    inputSchema: s.object("Input for fetching Baidu Netdisk file metadata.", {
      fileIds: s.array("The Baidu Netdisk fs_id values to fetch.", fileIdSchema, {
        minItems: 1,
        maxItems: 100,
      }),
    }),
    outputSchema: s.object("The normalized metadata items found by Baidu Netdisk.", {
      items: s.array("The found items ordered by the input file IDs.", fileSchema),
    }),
  }),
  defineProviderAction("baidu_netdisk", {
    name: "search_files",
    description: "Search up to 500 files and folders within the Baidu Netdisk app directory.",
    requiredScopes: [baiduNetdiskConnectorScopes.filesRead],
    providerPermissions: [baiduNetdiskProviderScopes.netdisk],
    inputSchema: searchInputSchema,
    outputSchema: s.object("One bounded Baidu Netdisk keyword search result.", {
      items: s.array("The normalized matching files and folders.", fileSchema),
      truncated: s.boolean("Whether Baidu reports more matches than this bounded result."),
    }),
  }),
  defineProviderAction("baidu_netdisk", {
    name: "semantic_search_files",
    description: "Search files in the configured Baidu Netdisk app directory using a natural-language description.",
    requiredScopes: [baiduNetdiskConnectorScopes.filesRead],
    providerPermissions: [baiduNetdiskProviderScopes.netdisk],
    inputSchema: semanticSearchInputSchema,
    outputSchema: s.object("One bounded Baidu Netdisk semantic search result.", {
      items: s.array("The normalized semantic matches.", semanticFileSchema),
      truncated: s.boolean("Whether Baidu reports that more semantic matches may be available."),
    }),
  }),
  defineProviderAction("baidu_netdisk", {
    name: "upload_file_from_url",
    description: "Download one public URL and upload its bytes to the configured Baidu Netdisk app directory.",
    requiredScopes: [baiduNetdiskConnectorScopes.filesWrite],
    providerPermissions: [baiduNetdiskProviderScopes.netdisk],
    inputSchema: s.object(
      "Input for uploading one public URL to Baidu Netdisk.",
      {
        fileUrl: publicFileUrlSchema,
        destinationPath: userPath("The app-relative destination file path.", false),
        conflictStrategy: s.optional(uploadConflictStrategySchema),
      },
      { optional: ["conflictStrategy"] },
    ),
    outputSchema: uploadedFileSchema,
  }),
  defineProviderAction("baidu_netdisk", {
    name: "create_text_file",
    description: "Create one UTF-8 text file of up to 4 MiB in the configured Baidu Netdisk app directory.",
    requiredScopes: [baiduNetdiskConnectorScopes.filesWrite],
    providerPermissions: [baiduNetdiskProviderScopes.netdisk],
    inputSchema: s.object(
      "Input for creating one UTF-8 Baidu Netdisk text file.",
      {
        path: userPath("The app-relative destination file path.", false),
        content: s.string("The UTF-8 text content, limited to 4 MiB after encoding.", {
          maxLength: 4 * 1024 * 1024,
        }),
        conflictStrategy: s.optional(uploadConflictStrategySchema),
      },
      { optional: ["conflictStrategy"] },
    ),
    outputSchema: uploadedFileSchema,
  }),
  defineProviderAction("baidu_netdisk", {
    name: "create_folder",
    description: "Create one folder below the configured Baidu Netdisk app directory.",
    requiredScopes: [baiduNetdiskConnectorScopes.filesWrite],
    providerPermissions: [baiduNetdiskProviderScopes.netdisk],
    inputSchema: s.object(
      "Input for creating one Baidu Netdisk folder.",
      {
        path: userPath("The app-relative path of the folder to create.", false),
        conflictStrategy: s.optional(
          s.withDefault(s.stringEnum("How to handle an existing folder path.", ["fail", "rename"]), "fail"),
        ),
      },
      { optional: ["conflictStrategy"] },
    ),
    outputSchema: fileSchema,
  }),
  defineProviderAction("baidu_netdisk", {
    name: "copy",
    description: "Synchronously copy one file or folder within the Baidu Netdisk app directory.",
    requiredScopes: [baiduNetdiskConnectorScopes.filesWrite],
    providerPermissions: [baiduNetdiskProviderScopes.netdisk],
    inputSchema: relocateInputSchema("copy"),
    outputSchema: managementOutputSchema,
  }),
  defineProviderAction("baidu_netdisk", {
    name: "move",
    description: "Synchronously move one file or folder within the Baidu Netdisk app directory.",
    requiredScopes: [baiduNetdiskConnectorScopes.filesWrite],
    providerPermissions: [baiduNetdiskProviderScopes.netdisk],
    inputSchema: relocateInputSchema("mov"),
    outputSchema: managementOutputSchema,
  }),
  defineProviderAction("baidu_netdisk", {
    name: "rename",
    description: "Synchronously rename one file or folder within the Baidu Netdisk app directory.",
    requiredScopes: [baiduNetdiskConnectorScopes.filesWrite],
    providerPermissions: [baiduNetdiskProviderScopes.netdisk],
    inputSchema: s.object(
      "Input for renaming one Baidu Netdisk file or folder.",
      {
        sourcePath: userPath("The app-relative source path.", false),
        newName: itemNameSchema,
        conflictStrategy: s.optional(conflictStrategySchema),
      },
      { optional: ["conflictStrategy"] },
    ),
    outputSchema: managementOutputSchema,
  }),
  defineProviderAction("baidu_netdisk", {
    name: "delete",
    description: "Delete one file or folder within the configured Baidu Netdisk app directory.",
    requiredScopes: [baiduNetdiskConnectorScopes.filesDelete],
    providerPermissions: [baiduNetdiskProviderScopes.netdisk],
    inputSchema: s.object("Input for deleting one Baidu Netdisk file or folder.", {
      path: userPath("The app-relative path to delete.", false),
    }),
    outputSchema: managementOutputSchema,
  }),
];
