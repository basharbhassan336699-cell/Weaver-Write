import { createHash } from "node:crypto";
import { createWriteStream } from "node:fs";
import { mkdtemp, open, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import { compactObject, optionalInteger, optionalString } from "../../core/cast.ts";
import { assertPublicHttpUrl } from "../../core/request.ts";
import { providerFetch, ProviderRequestError } from "../provider-runtime.ts";
import { baiduNetdiskFileCategories, baiduNetdiskSemanticMatchSources } from "./actions.ts";

const baiduPanBaseUrl = "https://pan.baidu.com";
const baiduUploadLocatorBaseUrl = "https://d.pcs.baidu.com";
const mebibyte = 1024 * 1024;
const textUploadMaxBytes = 4 * mebibyte;
const losslessIntegerKeys = new Set(["fs_id", "fsid", "pid", "uk", "request_id", "cursor"]);
const semanticSourceByCode = new Map<number, (typeof baiduNetdiskSemanticMatchSources)[number]>([
  [4, "filename"],
  [5, "image_ocr"],
  [11, "document_text"],
  [7, "document_semantic"],
  [8, "video_semantic"],
  [9, "audio_semantic"],
  [14, "image_semantic"],
  [13, "card"],
]);
const uploadProfileByMembership = {
  free: { chunkSizeBytes: 4 * mebibyte, maxSizeBytes: 4 * 1024 * mebibyte },
  vip: { chunkSizeBytes: 16 * mebibyte, maxSizeBytes: 10 * 1024 * mebibyte },
  svip: { chunkSizeBytes: 32 * mebibyte, maxSizeBytes: 20 * 1024 * mebibyte },
} as const;

type BaiduRequestPhase = "read" | "write";

export type BaiduNetdiskActionContext = {
  accessToken: string;
  appDirectoryPath: string;
  fetcher: typeof fetch;
  signal?: AbortSignal;
};

export interface BaiduNetdiskAccount {
  accountId: string;
  accountLabel: string;
  avatarUrl: string | null;
  membership: "free" | "vip" | "svip" | null;
  providerMetadata: Record<string, unknown>;
}

export function requireBaiduNetdiskAppDirectoryPath(value: unknown): string {
  const path = optionalString(value);
  const prefix = "/apps/";
  const segment = path?.startsWith(prefix) ? path.slice(prefix.length) : "";
  if (
    !path ||
    segment.length === 0 ||
    segment === "." ||
    segment === ".." ||
    segment.includes("/") ||
    segment.includes("\\") ||
    segment.includes("\0")
  ) {
    throw new ProviderRequestError(400, "baidu_netdisk requires appDirectoryPath in the form /apps/{appname}");
  }
  return path;
}

function parseBaiduNetdiskJson(text: string): Record<string, unknown> {
  let value: unknown;
  try {
    value = JSON.parse(stringifyBaiduLosslessIntegers(text));
  } catch {
    throw new ProviderRequestError(502, "baidu_netdisk returned invalid JSON");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ProviderRequestError(502, "baidu_netdisk returned invalid JSON");
  }
  return value as Record<string, unknown>;
}

function stringifyBaiduLosslessIntegers(text: string) {
  const ranges: Array<[number, number]> = [];
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] !== '"') {
      continue;
    }
    const keyStart = index;
    const keyEnd = findJsonStringEnd(text, keyStart + 1);
    if (keyEnd < 0) {
      return text;
    }
    index = keyEnd;
    const colonIndex = skipJsonWhitespace(text, keyEnd + 1);
    if (text[colonIndex] !== ":") {
      continue;
    }

    let key: unknown;
    try {
      key = JSON.parse(text.slice(keyStart, keyEnd + 1));
    } catch {
      return text;
    }
    if (typeof key !== "string" || !losslessIntegerKeys.has(key)) {
      continue;
    }

    const valueStart = skipJsonWhitespace(text, colonIndex + 1);
    let valueEnd = valueStart;
    while (isDecimalDigit(text[valueEnd])) {
      valueEnd += 1;
    }
    if (
      valueEnd === valueStart ||
      (text[valueStart] === "0" && valueEnd > valueStart + 1) ||
      !isJsonPropertyDelimiter(text, valueEnd)
    ) {
      continue;
    }
    ranges.push([valueStart, valueEnd]);
  }

  if (ranges.length === 0) {
    return text;
  }
  let output = "";
  let offset = 0;
  for (const [start, end] of ranges) {
    output += `${text.slice(offset, start)}"${text.slice(start, end)}"`;
    offset = end;
  }
  return output + text.slice(offset);
}

function findJsonStringEnd(text: string, start: number) {
  for (let index = start; index < text.length; index += 1) {
    if (text[index] === "\\") {
      index += 1;
    } else if (text[index] === '"') {
      return index;
    }
  }
  return -1;
}

function skipJsonWhitespace(text: string, start: number) {
  let index = start;
  while (text[index] === " " || text[index] === "\t" || text[index] === "\n" || text[index] === "\r") {
    index += 1;
  }
  return index;
}

function isDecimalDigit(value: string | undefined) {
  return value != null && value >= "0" && value <= "9";
}

function isJsonPropertyDelimiter(text: string, start: number) {
  const delimiter = text[skipJsonWhitespace(text, start)];
  return delimiter === "," || delimiter === "}";
}

async function readBaiduJson(response: Response) {
  return parseBaiduNetdiskJson(await response.text());
}

export async function fetchBaiduNetdiskAccount(
  accessToken: string,
  fetcher: typeof fetch,
): Promise<BaiduNetdiskAccount> {
  const url = new URL("/rest/2.0/xpan/nas", baiduPanBaseUrl);
  url.searchParams.set("method", "uinfo");
  url.searchParams.set("vip_version", "v2");
  const payload = await requestBaiduNetdiskApi(url, accessToken, fetcher, "read");
  const accountId = requireLosslessId(payload.uk, "uk");
  const netdiskName = optionalString(payload.netdisk_name);
  const baiduName = optionalString(payload.baidu_name);
  return {
    accountId,
    accountLabel: netdiskName ?? baiduName ?? accountId,
    avatarUrl: optionalString(payload.avatar_url) ?? null,
    membership: normalizeMembership(payload.vip_type),
    providerMetadata: compactObject({
      uk: accountId,
      netdiskName,
      baiduName,
    }),
  };
}

function normalizeMembership(value: unknown): "free" | "vip" | "svip" | null {
  if (value === 0) return "free";
  if (value === 1) return "vip";
  if (value === 2) return "svip";
  return null;
}

function requireLosslessId(value: unknown, fieldName: string) {
  if (typeof value === "string" && value.length > 0) {
    return value;
  }
  throw new ProviderRequestError(502, `baidu_netdisk response is missing ${fieldName}`);
}

async function requestBaiduNetdiskApi(
  url: URL,
  accessToken: string,
  fetcher: typeof fetch,
  phase: BaiduRequestPhase,
  init: RequestInit = {},
) {
  url.searchParams.set("access_token", accessToken);
  let response: Response;
  try {
    response = await fetcher(url, {
      ...init,
      headers: {
        "user-agent": "pan.baidu.com",
        accept: "application/json",
        ...Object.fromEntries(new Headers(init.headers).entries()),
      },
    });
  } catch {
    throw new ProviderRequestError(502, "baidu_netdisk request failed");
  }
  const payload = await readBaiduJson(response);
  const errno = optionalInteger(payload.errno ?? payload.error_no ?? payload.error_code);
  if (!response.ok || (errno != null && errno !== 0)) {
    throw normalizeBaiduNetdiskError(errno, response.status, payload.request_id, phase);
  }
  return payload;
}

function normalizeBaiduNetdiskError(
  errno: number | undefined,
  status: number,
  requestId: unknown,
  phase: BaiduRequestPhase,
) {
  const data = compactObject({
    providerCode: errno,
    requestId: typeof requestId === "string" ? requestId : undefined,
  });
  if (status === 429 || errno === 20012 || errno === 31034) {
    return new ProviderRequestError(429, "baidu_netdisk rate limit exceeded", data);
  }
  if (errno === -6 || errno === 31045) {
    return new ProviderRequestError(401, "baidu_netdisk credential expired", data);
  }
  if (errno === 31024 || (errno === -7 && phase === "read")) {
    return new ProviderRequestError(403, "baidu_netdisk permission is missing", data);
  }
  if (errno === 20013 || errno === 20015) {
    return new ProviderRequestError(503, "baidu_netdisk application permission is not configured", data);
  }
  if (errno === 20011) {
    return new ProviderRequestError(503, "baidu_netdisk test application user limit was reached", data);
  }
  if ([2, 31023, 31062, 31064, 31364, 31365].includes(errno ?? Number.NaN) || (errno === -7 && phase === "write")) {
    return new ProviderRequestError(400, "baidu_netdisk rejected the input", data);
  }
  if (errno === -8 || errno === 31061) {
    return new ProviderRequestError(409, "baidu_netdisk target already exists", data);
  }
  if (errno === -3 || errno === -9 || errno === 31066) {
    return new ProviderRequestError(404, "baidu_netdisk item was not found", data);
  }
  if (errno === -10) {
    return new ProviderRequestError(507, "baidu_netdisk storage is full", data);
  }
  if (errno === 111) {
    return new ProviderRequestError(409, "baidu_netdisk has a conflicting file management task", data);
  }
  return new ProviderRequestError(502, "baidu_netdisk request failed", data);
}

export async function executeBaiduNetdiskAction(
  actionName: string,
  input: Record<string, unknown>,
  context: BaiduNetdiskActionContext,
): Promise<unknown> {
  validateBaiduNetdiskInput(actionName, input);
  switch (actionName) {
    case "get_current_account": {
      const account = await fetchBaiduNetdiskAccount(context.accessToken, context.fetcher);
      return {
        accountId: account.accountId,
        accountLabel: account.accountLabel,
        avatarUrl: account.avatarUrl,
        membership: account.membership,
      };
    }
    case "get_quota":
      return getQuota(context);
    case "list_files":
      return listFiles(input, context);
    case "get_file_metadata":
      return getFileMetadata(input, context);
    case "search_files":
      return searchFiles(input, context);
    case "semantic_search_files":
      return semanticSearchFiles(input, context);
    case "upload_file_from_url":
      return uploadFileFromUrl(input, context);
    case "create_text_file":
      return createTextFile(input, context);
    case "create_folder":
      return createFolder(input, context);
    case "copy":
    case "move":
    case "rename":
    case "delete":
      return manageFile(actionName, input, context);
    default:
      throw new ProviderRequestError(400, `unknown baidu_netdisk action: ${actionName}`);
  }
}

function validateBaiduNetdiskInput(actionName: string, input: Record<string, unknown>): void {
  for (const field of ["path", "sourcePath", "destinationPath", "destinationDirectoryPath"]) {
    if (input[field] !== undefined) requireUserPath(input[field], field, field === "path");
  }
  if (input.fileId !== undefined) requirePositiveUint64(input.fileId, "fileId");
  if (input.cursor !== undefined) requireDecimalString(input.cursor, "cursor", true);
  if (input.newName !== undefined) requireItemName(input.newName, "newName");
  if (Array.isArray(input.extensions)) {
    for (const extension of input.extensions) requireExtension(extension);
  }
  if (actionName === "list_files") {
    if (input.extensions !== undefined && input.categories === undefined) {
      throw new ProviderRequestError(400, "extensions requires at least one category");
    }
    if (input.categories !== undefined && (input.createdAfter !== undefined || input.modifiedAfter !== undefined)) {
      throw new ProviderRequestError(
        400,
        "Baidu Netdisk does not support combining category filters with createdAfter or modifiedAfter",
      );
    }
  }
}

function requireUserPath(value: unknown, fieldName: string, allowRoot: boolean): string {
  const path = optionalString(value);
  const validRoot = path === "/" && allowRoot;
  const segments = path?.startsWith("/") ? path.slice(1).split("/") : [];
  if (
    !path ||
    (!validRoot &&
      (path.endsWith("/") ||
        path.includes("\\") ||
        path.includes("\0") ||
        segments.some((segment) => segment.length === 0 || segment === "." || segment === "..")))
  ) {
    throw new ProviderRequestError(400, `${fieldName} must be an absolute app-relative path without traversal`);
  }
  return path;
}

function requireDecimalString(value: unknown, fieldName: string, allowZero: boolean): string {
  const text = typeof value === "string" ? value : "";
  const decimal = text.length > 0 && [...text].every((character) => character >= "0" && character <= "9");
  if (!decimal || (!allowZero && (text === "0" || text.startsWith("0")))) {
    throw new ProviderRequestError(400, `${fieldName} must be a decimal string`);
  }
  return text;
}

function requirePositiveUint64(value: unknown, fieldName: string): string {
  const text = requireDecimalString(value, fieldName, false);
  if (text.length > 20 || BigInt(text) > 18_446_744_073_709_551_615n) {
    throw new ProviderRequestError(400, `${fieldName} must be a positive uint64 decimal string`);
  }
  return text;
}

function requireItemName(value: unknown, fieldName: string): string {
  const name = optionalString(value);
  if (!name || name === "." || name === ".." || name.includes("/") || name.includes("\\") || name.includes("\0")) {
    throw new ProviderRequestError(400, `${fieldName} must be one name without path separators`);
  }
  return name;
}

function requireExtension(value: unknown): string {
  const extension = optionalString(value);
  if (
    !extension ||
    extension.startsWith(".") ||
    extension.includes(",") ||
    extension.includes("/") ||
    extension.includes("\\") ||
    extension.includes("\0") ||
    extension.includes(" ")
  ) {
    throw new ProviderRequestError(400, "extensions must omit leading dots, separators, commas, and spaces");
  }
  return extension;
}

const actionNames: string[] = [
  "get_current_account",
  "get_quota",
  "list_files",
  "get_file_metadata",
  "search_files",
  "semantic_search_files",
  "upload_file_from_url",
  "create_text_file",
  "create_folder",
  "copy",
  "move",
  "rename",
  "delete",
];

export const baiduNetdiskActionHandlers: Record<
  string,
  (input: Record<string, unknown>, context: BaiduNetdiskActionContext) => Promise<unknown>
> = Object.fromEntries(
  actionNames.map((actionName) => [
    actionName,
    (input: Record<string, unknown>, context: BaiduNetdiskActionContext) =>
      executeBaiduNetdiskAction(actionName, input, context),
  ]),
);

async function getQuota(context: BaiduNetdiskActionContext) {
  const url = new URL("/api/quota", baiduPanBaseUrl);
  url.searchParams.set("checkfree", "1");
  url.searchParams.set("checkexpire", "1");
  const payload = await requestBaiduNetdiskApi(url, context.accessToken, context.fetcher, "read");
  const totalBytes = requireInteger(payload.total, "total");
  const usedBytes = requireInteger(payload.used, "used");
  return {
    totalBytes,
    usedBytes,
    remainingBytes: Math.max(totalBytes - usedBytes, 0),
    freeQuotaBytes: requireInteger(payload.free, "free"),
    expiresWithinSevenDays: payload.expire === true,
  };
}

async function listFiles(input: Record<string, unknown>, context: BaiduNetdiskActionContext) {
  const recursive = input.recursive === true;
  const categories = Array.isArray(input.categories) ? (input.categories as string[]) : [];
  const extensions = Array.isArray(input.extensions) ? (input.extensions as string[]) : [];
  const hasTimeFilter = input.createdAfter != null || input.modifiedAfter != null;
  const usesCategoryList = categories.length > 0;
  const usesListAll = recursive || hasTimeFilter;
  const url = new URL(
    usesCategoryList || usesListAll ? "/rest/2.0/xpan/multimedia" : "/rest/2.0/xpan/file",
    baiduPanBaseUrl,
  );
  const cursor = String(input.cursor ?? "0");
  const limit = requireInteger(input.limit, "limit");
  const providerPath = toProviderPath(context.appDirectoryPath, String(input.path));
  url.searchParams.set("method", usesCategoryList ? "categorylist" : usesListAll ? "listall" : "list");
  url.searchParams.set(usesCategoryList ? "parent_path" : usesListAll ? "path" : "dir", providerPath);
  if (input.sortBy != null) {
    url.searchParams.set("order", normalizeSortBy(input.sortBy));
  }
  if (input.sortOrder != null) {
    url.searchParams.set("desc", input.sortOrder === "descending" ? "1" : "0");
  }
  url.searchParams.set("start", cursor);
  url.searchParams.set("limit", String(limit));
  if (usesCategoryList) {
    url.searchParams.set("category", normalizeCategories(categories).join(","));
    url.searchParams.set("recursion", recursive ? "1" : "0");
    url.searchParams.set("show_dir", "0");
    if (extensions.length > 0) {
      url.searchParams.set("ext", extensions.map((extension) => extension.toLowerCase()).join(","));
    }
  } else if (usesListAll) {
    url.searchParams.set("recursion", recursive ? "1" : "0");
    if (input.createdAfter != null) {
      url.searchParams.set("ctime", toUnixSeconds(input.createdAfter, "createdAfter"));
    }
    if (input.modifiedAfter != null) {
      url.searchParams.set("mtime", toUnixSeconds(input.modifiedAfter, "modifiedAfter"));
    }
  }
  const payload = await requestBaiduNetdiskApi(url, context.accessToken, context.fetcher, "read");
  const items = readObjectArray(payload.list).map((item) => normalizeBaiduNetdiskFile(item, context.appDirectoryPath));
  let nextCursor: string | null = null;
  if (usesCategoryList || usesListAll) {
    if (payload.has_more === 1) {
      nextCursor = requireLosslessId(payload.cursor, "cursor");
    }
  } else if (items.length === limit) {
    nextCursor = (BigInt(cursor) + BigInt(items.length)).toString();
  }
  return { items, nextCursor };
}

function normalizeCategories(categories: string[]) {
  const values = new Set<number>();
  for (const category of categories) {
    const index = baiduNetdiskFileCategories.indexOf(category as (typeof baiduNetdiskFileCategories)[number]);
    if (index >= 0) {
      values.add(index + 1);
    }
  }
  return [...values];
}

function toUnixSeconds(value: unknown, fieldName: string) {
  const milliseconds = Date.parse(String(value));
  if (!Number.isFinite(milliseconds)) {
    throw new ProviderRequestError(400, `${fieldName} must be an ISO 8601 timestamp`);
  }
  return String(Math.floor(milliseconds / 1000));
}

function normalizeSortBy(value: unknown) {
  if (value === "modifiedTime") return "time";
  if (value === "size") return "size";
  return "name";
}

async function getFileMetadata(input: Record<string, unknown>, context: BaiduNetdiskActionContext) {
  const fileIds = input.fileIds as string[];
  const url = new URL("/rest/2.0/xpan/multimedia", baiduPanBaseUrl);
  url.searchParams.set("method", "filemetas");
  url.searchParams.set("fsids", `[${fileIds.join(",")}]`);
  const payload = await requestBaiduNetdiskApi(url, context.accessToken, context.fetcher, "read");
  const itemById = new Map(
    readObjectArray(payload.list).map((item) => {
      const normalized = normalizeBaiduNetdiskFile(item, context.appDirectoryPath);
      return [normalized.id, normalized] as const;
    }),
  );
  return { items: fileIds.flatMap((fileId) => itemById.get(fileId) ?? []) };
}

async function searchFiles(input: Record<string, unknown>, context: BaiduNetdiskActionContext) {
  const url = new URL("/rest/2.0/xpan/file", baiduPanBaseUrl);
  url.searchParams.set("method", "search");
  url.searchParams.set("key", String(input.query));
  url.searchParams.set("dir", toProviderPath(context.appDirectoryPath, String(input.path)));
  url.searchParams.set("num", "500");
  if (input.recursive === true) {
    url.searchParams.set("recursion", "1");
  }
  const category = baiduNetdiskFileCategories.indexOf(input.category as (typeof baiduNetdiskFileCategories)[number]);
  if (category >= 0) {
    url.searchParams.set("category", String(category + 1));
  }
  const payload = await requestBaiduNetdiskApi(url, context.accessToken, context.fetcher, "read");
  return {
    items: readObjectArray(payload.list).map((item) => normalizeBaiduNetdiskFile(item, context.appDirectoryPath)),
    truncated: payload.has_more === 1,
  };
}

async function semanticSearchFiles(input: Record<string, unknown>, context: BaiduNetdiskActionContext) {
  const account = await fetchBaiduNetdiskAccount(context.accessToken, context.fetcher);
  const providerPath = toProviderPath(context.appDirectoryPath, String(input.path));
  const url = new URL("/xpan/unisearch", baiduPanBaseUrl);
  url.searchParams.set("scene", "mcpserver");
  url.searchParams.set("query", String(input.query));
  url.searchParams.set("dirs", `[{"uk":${account.accountId},"path":${JSON.stringify(providerPath)}}]`);
  url.searchParams.set("num", String(input.limit));
  url.searchParams.set("stream", "0");
  url.searchParams.set("search_type", "1");
  const payload = await requestBaiduNetdiskApi(url, context.accessToken, context.fetcher, "read", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}",
  });
  const items = readObjectArray(payload.data).flatMap((group) => {
    const groupSource = optionalInteger(group.source);
    return readObjectArray(group.list).map((item) => {
      const normalized = normalizeBaiduNetdiskFile({ ...item, fs_id: item.fsid }, context.appDirectoryPath);
      const source = optionalInteger(item.source) ?? groupSource;
      return {
        ...normalized,
        matchSource: source == null ? null : (semanticSourceByCode.get(source) ?? null),
        matchedContent: optionalString(item.content) ?? null,
        ocrText: optionalString(item.ocr) ?? null,
        passageId: item.pid == null ? null : requireLosslessId(item.pid, "pid"),
      };
    });
  });
  return {
    items,
    truncated: payload.is_end === false,
  };
}

async function uploadFileFromUrl(input: Record<string, unknown>, context: BaiduNetdiskActionContext) {
  const account = await fetchBaiduNetdiskAccount(context.accessToken, context.fetcher);
  const profile = uploadProfileByMembership[account.membership ?? "free"];
  const fileUrl = assertPublicHttpUrl(String(input.fileUrl), {
    fieldName: "fileUrl",
    createError: (message) => new ProviderRequestError(400, message),
  });
  let response: Response;
  try {
    response = await providerFetch(fileUrl, { signal: context.signal });
  } catch (error) {
    if (error instanceof ProviderRequestError) {
      throw error;
    }
    throw new ProviderRequestError(502, "baidu_netdisk failed to fetch fileUrl");
  }
  if (!response.ok) {
    await response.body?.cancel().catch(() => {});
    throw new ProviderRequestError(400, `fileUrl returned HTTP ${response.status}`);
  }
  const contentLength = parseContentLength(response.headers.get("content-length"));
  if (contentLength != null && contentLength > profile.maxSizeBytes) {
    await response.body?.cancel().catch(() => {});
    throw uploadTooLargeError(profile.maxSizeBytes);
  }
  const staged = await stageResponseForUpload(response, profile.chunkSizeBytes, profile.maxSizeBytes);
  try {
    return await uploadStagedFile(staged, String(input.destinationPath), input.conflictStrategy, context);
  } finally {
    await staged.cleanup();
  }
}

async function createTextFile(input: Record<string, unknown>, context: BaiduNetdiskActionContext) {
  const bytes = new TextEncoder().encode(String(input.content));
  if (bytes.byteLength > textUploadMaxBytes) {
    throw uploadTooLargeError(textUploadMaxBytes);
  }
  const staged = await stageBytesForUpload(bytes, textUploadMaxBytes);
  try {
    return await uploadStagedFile(staged, String(input.path), input.conflictStrategy, context);
  } finally {
    await staged.cleanup();
  }
}

interface StagedBaiduUpload {
  filePath: string;
  sizeBytes: number;
  chunkSizeBytes: number;
  blockMd5s: string[];
  cleanup(): Promise<void>;
}

async function stageResponseForUpload(
  response: Response,
  chunkSizeBytes: number,
  maxSizeBytes: number,
): Promise<StagedBaiduUpload> {
  if (!response.body) {
    throw new ProviderRequestError(400, "fileUrl returned an empty body");
  }
  const directory = await mkdtemp(join(tmpdir(), "oomol-connector-baidu-netdisk-"));
  const filePath = join(directory, "upload");
  const blockMd5s: string[] = [];
  let blockHash = createHash("md5");
  let blockSize = 0;
  let sizeBytes = 0;
  const hashAndLimit = new Transform({
    transform(chunk, _encoding, callback) {
      const bytes = chunk instanceof Uint8Array ? chunk : Buffer.from(chunk);
      sizeBytes += bytes.byteLength;
      if (sizeBytes > maxSizeBytes) {
        callback(uploadTooLargeError(maxSizeBytes));
        return;
      }
      let offset = 0;
      while (offset < bytes.byteLength) {
        const length = Math.min(chunkSizeBytes - blockSize, bytes.byteLength - offset);
        blockHash.update(bytes.subarray(offset, offset + length));
        blockSize += length;
        offset += length;
        if (blockSize === chunkSizeBytes) {
          blockMd5s.push(blockHash.digest("hex"));
          blockHash = createHash("md5");
          blockSize = 0;
        }
      }
      callback(null, chunk);
    },
  });
  try {
    await pipeline(Readable.fromWeb(response.body as never), hashAndLimit, createWriteStream(filePath));
    if (blockSize > 0 || sizeBytes === 0) {
      blockMd5s.push(blockHash.digest("hex"));
    }
    return stagedUpload(directory, filePath, sizeBytes, chunkSizeBytes, blockMd5s);
  } catch (error) {
    await rm(directory, { recursive: true, force: true }).catch(() => {});
    throw error;
  }
}

async function stageBytesForUpload(bytes: Uint8Array, chunkSizeBytes: number): Promise<StagedBaiduUpload> {
  const directory = await mkdtemp(join(tmpdir(), "oomol-connector-baidu-netdisk-"));
  const filePath = join(directory, "upload");
  try {
    await writeFile(filePath, bytes);
    return stagedUpload(directory, filePath, bytes.byteLength, chunkSizeBytes, [
      createHash("md5").update(bytes).digest("hex"),
    ]);
  } catch (error) {
    await rm(directory, { recursive: true, force: true }).catch(() => {});
    throw error;
  }
}

function stagedUpload(
  directory: string,
  filePath: string,
  sizeBytes: number,
  chunkSizeBytes: number,
  blockMd5s: string[],
): StagedBaiduUpload {
  return {
    filePath,
    sizeBytes,
    chunkSizeBytes,
    blockMd5s,
    cleanup: async () => {
      await rm(directory, { recursive: true, force: true }).catch(() => {});
    },
  };
}

async function uploadStagedFile(
  staged: StagedBaiduUpload,
  destinationPath: string,
  conflictStrategy: unknown,
  context: BaiduNetdiskActionContext,
) {
  const providerPath = toProviderPath(context.appDirectoryPath, destinationPath);
  const blockList = JSON.stringify(staged.blockMd5s);
  const rtype = normalizeUploadConflictStrategy(conflictStrategy);
  const precreateUrl = new URL("/rest/2.0/xpan/file", baiduPanBaseUrl);
  precreateUrl.searchParams.set("method", "precreate");
  const precreate = await requestBaiduNetdiskApi(precreateUrl, context.accessToken, context.fetcher, "write", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      path: providerPath,
      size: String(staged.sizeBytes),
      isdir: "0",
      autoinit: "1",
      rtype,
      block_list: blockList,
    }),
  });
  if (precreate.path != null && precreate.path !== providerPath) {
    throw new ProviderRequestError(502, "baidu_netdisk returned an unexpected upload path");
  }
  if (optionalInteger(precreate.return_type) === 2) {
    return {
      id: null,
      name: basename(destinationPath),
      path: destinationPath,
      kind: "file" as const,
      category: null,
      sizeBytes: staged.sizeBytes,
      createdAt: null,
      modifiedAt: null,
      cloudMd5: null,
    };
  }
  const uploadId = requireString(precreate.uploadid, "uploadid");
  const partIndexes = normalizeUploadPartIndexes(precreate.block_list, staged.blockMd5s.length);
  const uploadBaseUrl = await locateBaiduUploadServer(providerPath, uploadId, context);
  const file = await open(staged.filePath, "r");
  try {
    for (const partIndex of partIndexes) {
      const bytes = await readUploadPart(file, staged, partIndex);
      const form = new FormData();
      form.set("file", new Blob([bytes]), basename(destinationPath));
      const uploadUrl = new URL("/rest/2.0/pcs/superfile2", uploadBaseUrl);
      uploadUrl.searchParams.set("method", "upload");
      uploadUrl.searchParams.set("type", "tmpfile");
      uploadUrl.searchParams.set("path", providerPath);
      uploadUrl.searchParams.set("uploadid", uploadId);
      uploadUrl.searchParams.set("partseq", String(partIndex));
      const uploaded = await requestBaiduNetdiskApi(uploadUrl, context.accessToken, context.fetcher, "write", {
        method: "POST",
        body: form,
      });
      if (optionalString(uploaded.md5) !== staged.blockMd5s[partIndex]) {
        throw new ProviderRequestError(502, "baidu_netdisk returned an unexpected uploaded part md5");
      }
    }
  } finally {
    await file.close();
  }
  const createUrl = new URL("/rest/2.0/xpan/file", baiduPanBaseUrl);
  createUrl.searchParams.set("method", "create");
  const created = await requestBaiduNetdiskApi(createUrl, context.accessToken, context.fetcher, "write", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      path: providerPath,
      size: String(staged.sizeBytes),
      isdir: "0",
      block_list: blockList,
      uploadid: uploadId,
      rtype,
    }),
  });
  return normalizeBaiduNetdiskFile(created, context.appDirectoryPath);
}

async function locateBaiduUploadServer(providerPath: string, uploadId: string, context: BaiduNetdiskActionContext) {
  const url = new URL("/rest/2.0/pcs/file", baiduUploadLocatorBaseUrl);
  url.searchParams.set("method", "locateupload");
  url.searchParams.set("appid", "250528");
  url.searchParams.set("path", providerPath);
  url.searchParams.set("uploadid", uploadId);
  url.searchParams.set("upload_version", "2.0");
  const payload = await requestBaiduNetdiskApi(url, context.accessToken, context.fetcher, "write");
  if (!Array.isArray(payload.servers)) {
    throw new ProviderRequestError(502, "baidu_netdisk response is missing upload servers");
  }
  for (const item of payload.servers) {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      continue;
    }
    const server = optionalString((item as Record<string, unknown>).server);
    if (!server) {
      continue;
    }
    try {
      const candidate = new URL(server);
      if (candidate.protocol === "https:" && candidate.hostname.endsWith(".pcs.baidu.com")) {
        return candidate.origin;
      }
    } catch {
      continue;
    }
  }
  throw new ProviderRequestError(502, "baidu_netdisk returned no trusted HTTPS upload server");
}

function normalizeUploadPartIndexes(value: unknown, partCount: number) {
  if (!Array.isArray(value)) {
    throw new ProviderRequestError(502, "baidu_netdisk response is missing block_list");
  }
  const indexes = value.length === 0 ? [0] : value;
  return indexes.map((item) => {
    const index = optionalInteger(item);
    if (index == null || index < 0 || index >= partCount) {
      throw new ProviderRequestError(502, "baidu_netdisk returned an invalid upload part index");
    }
    return index;
  });
}

async function readUploadPart(file: Awaited<ReturnType<typeof open>>, staged: StagedBaiduUpload, partIndex: number) {
  const position = partIndex * staged.chunkSizeBytes;
  const length = Math.min(staged.chunkSizeBytes, staged.sizeBytes - position);
  const bytes = new Uint8Array(length);
  const result = await file.read(bytes, 0, length, position);
  if (result.bytesRead !== length) {
    throw new ProviderRequestError(502, "baidu_netdisk upload staging file is incomplete");
  }
  return bytes;
}

function normalizeUploadConflictStrategy(value: unknown) {
  if (value === "rename") return "1";
  if (value === "overwrite") return "3";
  return "0";
}

function parseContentLength(value: string | null) {
  if (value == null) {
    return null;
  }
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : null;
}

function uploadTooLargeError(maxSizeBytes: number) {
  return new ProviderRequestError(
    400,
    `file exceeds the ${maxSizeBytes} byte Baidu Netdisk upload limit for this action`,
  );
}

function requireString(value: unknown, fieldName: string) {
  const string = optionalString(value);
  if (!string) {
    throw new ProviderRequestError(502, `baidu_netdisk response is missing ${fieldName}`);
  }
  return string;
}

function toProviderPath(appDirectoryPath: string, path: string) {
  return path === "/" ? appDirectoryPath : `${appDirectoryPath}${path}`;
}

function toUserPath(appDirectoryPath: string, path: unknown) {
  if (typeof path !== "string") {
    throw new ProviderRequestError(502, "baidu_netdisk response is missing path");
  }
  if (path === appDirectoryPath) {
    return "/";
  }
  const prefix = `${appDirectoryPath}/`;
  if (!path.startsWith(prefix)) {
    throw new ProviderRequestError(502, "baidu_netdisk returned an item outside the configured app directory");
  }
  return path.slice(appDirectoryPath.length);
}

function normalizeBaiduNetdiskFile(item: Record<string, unknown>, appDirectoryPath: string) {
  const path = toUserPath(appDirectoryPath, item.path);
  const isFolder = item.isdir === 1;
  const name =
    optionalString(item.server_filename) ?? optionalString(item.filename) ?? path.slice(path.lastIndexOf("/") + 1);
  return {
    id: requireLosslessId(item.fs_id, "fs_id"),
    name,
    path,
    kind: isFolder ? ("folder" as const) : ("file" as const),
    category: isFolder ? null : normalizeCategory(item.category),
    sizeBytes: isFolder ? null : (optionalInteger(item.size) ?? null),
    createdAt: normalizeTimestamp(item.server_ctime ?? item.ctime),
    modifiedAt: normalizeTimestamp(item.server_mtime ?? item.mtime),
    cloudMd5: optionalString(item.md5) ?? null,
  };
}

function normalizeCategory(value: unknown) {
  const category = optionalInteger(value);
  return category && category >= 1 && category <= baiduNetdiskFileCategories.length
    ? baiduNetdiskFileCategories[category - 1]!
    : "other";
}

function normalizeTimestamp(value: unknown) {
  const seconds = optionalInteger(value);
  if (seconds == null || seconds < 0) {
    return null;
  }
  const date = new Date(seconds * 1000);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function requireInteger(value: unknown, fieldName: string) {
  const integer = optionalInteger(value);
  if (integer == null) {
    throw new ProviderRequestError(502, `baidu_netdisk response is missing ${fieldName}`);
  }
  return integer;
}

function readObjectArray(value: unknown) {
  if (!Array.isArray(value)) {
    throw new ProviderRequestError(502, "baidu_netdisk response is missing list");
  }
  return value.map((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      throw new ProviderRequestError(502, "baidu_netdisk returned an invalid item");
    }
    return item as Record<string, unknown>;
  });
}

async function createFolder(input: Record<string, unknown>, context: BaiduNetdiskActionContext) {
  const url = new URL("/rest/2.0/xpan/file", baiduPanBaseUrl);
  url.searchParams.set("method", "create");
  const payload = await requestBaiduNetdiskApi(url, context.accessToken, context.fetcher, "write", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      path: toProviderPath(context.appDirectoryPath, String(input.path)),
      isdir: "1",
      rtype: input.conflictStrategy === "rename" ? "1" : "0",
    }),
  });
  return normalizeBaiduNetdiskFile(payload, context.appDirectoryPath);
}

async function manageFile(
  operation: "copy" | "move" | "rename" | "delete",
  input: Record<string, unknown>,
  context: BaiduNetdiskActionContext,
) {
  const sourcePath = String(operation === "delete" ? input.path : input.sourcePath);
  const url = new URL("/rest/2.0/xpan/file", baiduPanBaseUrl);
  url.searchParams.set("method", "filemanager");
  url.searchParams.set("opera", operation);
  const body = new URLSearchParams({
    async: "0",
    filelist: JSON.stringify([
      operation === "delete"
        ? toProviderPath(context.appDirectoryPath, sourcePath)
        : compactObject({
            path: toProviderPath(context.appDirectoryPath, sourcePath),
            dest:
              operation === "copy" || operation === "move"
                ? toProviderPath(context.appDirectoryPath, String(input.destinationDirectoryPath))
                : undefined,
            newname: optionalString(input.newName),
          }),
    ]),
  });
  if (operation !== "delete") {
    body.set("ondup", normalizeConflictStrategy(input.conflictStrategy));
  }
  const payload = await requestBaiduNetdiskApi(url, context.accessToken, context.fetcher, "write", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  const topLevelErrno = optionalInteger(payload.errno);
  if (topLevelErrno !== 0) {
    throw normalizeBaiduNetdiskError(topLevelErrno, 200, payload.request_id, "write");
  }
  const info = readObjectArray(payload.info);
  if (info.length !== 1) {
    throw new ProviderRequestError(502, "baidu_netdisk synchronous file operation returned invalid info");
  }
  const item = info[0]!;
  const errno = optionalInteger(item.errno);
  if (errno !== 0) {
    throw normalizeBaiduNetdiskError(errno, 200, payload.request_id, "write");
  }
  return {
    sourcePath,
    path: item.path == null ? null : toUserPath(context.appDirectoryPath, item.path),
  };
}

function normalizeConflictStrategy(value: unknown) {
  if (value === "rename") return "newcopy";
  if (value === "overwrite") return "overwrite";
  if (value === "skip") return "skip";
  return "fail";
}
