import webConfig from "@/constants/common-env";
import { getStoredAuthKey, type AuthSession } from "@/store/auth";

import { httpRequest } from "@/lib/request";

export type { AuthSession };

export type AccountType = "Free" | "Plus" | "ProLite" | "Pro" | "Team";
export type AccountStatus = "正常" | "限流" | "异常" | "禁用";
export type ImageModel = "auto" | "gpt-image-1" | "gpt-image-2" | "codex-gpt-image-2" | string;
export type ImageSizeOption = "1:1" | "4:3" | "3:4" | "3:2" | "16:9" | "21:9" | "9:16";
export type ImageSizeValue = string;
export type ImageQuality = "low" | "medium" | "high";
export type ImageResolutionTier = "sd" | "2k" | "4k";

export const IMAGE_SIZE_OPTIONS: ImageSizeOption[] = ["1:1", "4:3", "3:4", "3:2", "16:9", "21:9", "9:16"];
export const IMAGE_QUALITY_OPTIONS: ImageQuality[] = ["low", "medium", "high"];
export const IMAGE_RESOLUTION_TIERS: ImageResolutionTier[] = ["sd", "2k", "4k"];
export const IMAGE_RESOLUTION_PRESETS: Record<string, Record<ImageResolutionTier, string>> = {
  "1:1": { sd: "1248x1248", "2k": "2048x2048", "4k": "2880x2880" },
  "4:3": { sd: "1440x1072", "2k": "2048x1536", "4k": "3264x2448" },
  "3:4": { sd: "1072x1440", "2k": "1536x2048", "4k": "2448x3264" },
  "3:2": { sd: "1536x1024", "2k": "2160x1440", "4k": "3456x2304" },
  "16:9": { sd: "1664x928", "2k": "2560x1440", "4k": "3840x2160" },
  "21:9": { sd: "1904x816", "2k": "3360x1440", "4k": "3808x1632" },
  "9:16": { sd: "928x1664", "2k": "1440x2560", "4k": "2160x3840" },
};

export type Account = {
  id: string;
  access_token: string;
  type: AccountType;
  status: AccountStatus;
  quota: number;
  imageQuotaUnknown?: boolean;
  email?: string | null;
  user_id?: string | null;
  limits_progress?: Array<{
    feature_name?: string;
    remaining?: number;
    reset_after?: string;
  }>;
  default_model_slug?: string | null;
  restoreAt?: string | null;
  success: number;
  fail: number;
  lastUsedAt: string | null;
};

type AccountListResponse = {
  items: Account[];
};

type AccountMutationResponse = {
  items: Account[];
  added?: number;
  skipped?: number;
  removed?: number;
  refreshed?: number;
  errors?: Array<{ access_token: string; error: string }>;
};

type AccountRefreshResponse = {
  items: Account[];
  refreshed: number;
  errors: Array<{ access_token: string; error: string }>;
};

type AccountUpdateResponse = {
  item: Account;
  items: Account[];
};

export type SettingsConfig = {
  proxy: string;
  base_url?: string;
  image_storage_backend?: "local" | "hf_datasets" | string;
  image_hf_dataset_repo?: string;
  image_hf_dataset_path?: string;
  image_hf_token?: string;
  image_hf_dataset_url?: string;
  image_url_prefix?: string;
  image_url_template?: string;
  "auth-key"?: string;
  port?: number | string;
  refresh_account_interval_minute?: number | string;
  image_failure_strategy?: "fail" | "retry" | "placeholder" | string;
  image_retry_count?: number | string;
  image_parallel_attempts?: number | string;
  image_placeholder_path?: string;
  image_response_format?: "b64_json" | "url" | string;
  image_url_include_b64_when_requested?: boolean;
  image_thumbnail_max_size?: number | string;
  image_thumbnail_quality?: number | string;
  image_wall_thumbnail_max_size?: number | string;
  openai_compat_image_task_tracking_enabled?: boolean;
  openai_compat_image_gallery_enabled?: boolean;
  openai_compat_image_waterfall_enabled?: boolean;
  image_retention_days?: number | string;
  task_log_retention_days?: number | string;
  system_log_max_mb?: number | string;
  data_cleanup_enabled?: boolean;
  data_cleanup_interval_minutes?: number | string;
  [key: string]: unknown;
};

export type SettingsResponse = {
  config: SettingsConfig;
  effective_config?: SettingsConfig;
  env_overrides?: Record<string, string>;
};

export type ModelItem = {
  id: string;
  owned_by?: string;
};

export type ModelCatalogItem = {
  id: string;
  openai_id: string;
  capabilities: string[];
  owned_by?: string;
  async_supported?: boolean;
  image_options?: {
    size_choices?: string[];
    default_size?: string;
    response_format_choices?: string[];
    default_response_format?: string;
    quality_choices?: string[];
    default_quality?: string;
    resolution_presets?: Record<string, Record<string, string>>;
    supports_custom_size?: boolean;
    supports_multiple_reference_images?: boolean;
  } | null;
};

export type ImageResultItem = {
  b64_json?: string;
  url?: string;
  thumbnail_url?: string;
  markdown?: string;
  revised_prompt?: string;
};

export type PreviewImageItem = {
  id: string;
  src: string;
  job_id?: string;
  image_index?: number;
  type?: string | null;
  model?: string | null;
  prompt?: string | null;
  prompt_preview?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  api_key_id?: string | null;
  api_key_name?: string | null;
  url?: string | null;
  thumbnail_url?: string | null;
  relative_path?: string | null;
  thumbnail_relative_path?: string | null;
  wall_url?: string | null;
  wall_relative_path?: string | null;
  is_recommended?: boolean;
  is_pinned?: boolean;
  is_blocked?: boolean;
  markdown?: string | null;
};

export type APIKeyItem = {
  id: string;
  name: string;
  prefix: string;
  enabled: boolean;
  scopes: string[];
  allowed_models: string[];
  created_at: string;
  updated_at: string;
  last_used_at?: string | null;
  expires_at?: string | null;
  request_count: number;
  max_requests?: number | null;
  remaining_requests?: number | null;
  image_count: number;
  max_image_count?: number | null;
  remaining_image_count?: number | null;
};

export type AsyncJobStatus = "queued" | "running" | "succeeded" | "failed";
export type AsyncJobType =
  | "chat.completions"
  | "responses"
  | "images.generations"
  | "images.edits";

export type AsyncJobItem = {
  id: string;
  type: AsyncJobType | string;
  status: AsyncJobStatus | string;
  model: string;
  created_at: string;
  updated_at: string;
  log_path?: string | null;
  api_key_id?: string | null;
  api_key_name?: string | null;
  prompt?: string | null;
  prompt_preview?: string | null;
  requested_count?: number;
  size?: string | null;
  input_image_count?: number;
  result_ready?: boolean;
  result_count?: number;
  preview_images?: PreviewImageItem[];
  error?: { message?: string; code?: string; status_code?: number } | null;
};

export type AsyncJobSummary = {
  total: number;
  queued: number;
  running: number;
  succeeded: number;
  failed: number;
};

export type PaginatedAsyncJobsResponse = {
  items: AsyncJobItem[];
  total: number;
  limit: number;
  offset: number;
  summary: AsyncJobSummary;
};

export type PaginatedGalleryResponse = {
  items: AsyncJobItem[];
  total: number;
  limit: number;
  offset: number;
};

export type PaginatedWaterfallResponse = {
  items: PreviewImageItem[];
  total: number;
  limit: number;
  offset: number;
};

export type DataStatsCategory = {
  path: string;
  files: number;
  bytes: number;
};

export type DataStats = {
  root: string;
  generated_at: string;
  total_files: number;
  total_bytes: number;
  categories: Record<string, DataStatsCategory>;
};

export type DataCleanupResult = {
  enabled: boolean;
  run_at?: string;
  deleted: {
    images: { files: number; bytes: number };
    task_logs: { files: number; bytes: number };
    empty_image_dirs: number;
  };
  system_log: {
    before_bytes: number;
    after_bytes: number;
    trimmed_bytes: number;
  };
  stats: DataStats;
};

export async function login(authKey: string) {
  const normalizedAuthKey = String(authKey || "").trim();
  return httpRequest<{ ok: boolean; version: string; session: AuthSession }>("/auth/login", {
    method: "POST",
    body: {},
    headers: {
      Authorization: `Bearer ${normalizedAuthKey}`,
    },
    redirectOnUnauthorized: false,
  });
}

export async function fetchAccounts() {
  return httpRequest<AccountListResponse>("/api/accounts");
}

export async function createAccounts(tokens: string[]) {
  return httpRequest<AccountMutationResponse>("/api/accounts", {
    method: "POST",
    body: { tokens },
  });
}

export async function deleteAccounts(tokens: string[]) {
  return httpRequest<AccountMutationResponse>("/api/accounts", {
    method: "DELETE",
    body: { tokens },
  });
}

export async function refreshAccounts(accessTokens: string[]) {
  return httpRequest<AccountRefreshResponse>("/api/accounts/refresh", {
    method: "POST",
    body: { access_tokens: accessTokens },
  });
}

export async function updateAccount(
  accessToken: string,
  updates: {
    type?: AccountType;
    status?: AccountStatus;
    quota?: number;
  },
) {
  return httpRequest<AccountUpdateResponse>("/api/accounts/update", {
    method: "POST",
    body: {
      access_token: accessToken,
      ...updates,
    },
  });
}

export async function fetchModelList() {
  return httpRequest<{ object: string; data: ModelItem[] }>("/v1/models");
}

export async function fetchModelCatalog() {
  return httpRequest<{ items: ModelCatalogItem[]; openai_models_endpoint: string }>("/api/catalog/models");
}

export async function generateImage(
  prompt: string,
  options?: { model?: ImageModel; size?: ImageSizeValue; quality?: ImageQuality },
) {
  return httpRequest<{ created: number; data: ImageResultItem[] }>(
    "/v1/images/generations",
    {
      method: "POST",
      body: {
        prompt,
        ...(options?.model ? { model: options.model } : {}),
        ...(options?.size ? { size: options.size } : {}),
        ...(options?.quality ? { quality: options.quality } : {}),
        n: 1,
        response_format: "b64_json",
      },
    },
  );
}

export async function editImage(
  files: File | File[],
  prompt: string,
  options?: { model?: ImageModel; size?: ImageSizeValue },
) {
  const formData = new FormData();
  const uploadFiles = Array.isArray(files) ? files : [files];

  uploadFiles.forEach((file) => {
    formData.append("image", file);
  });
  formData.append("prompt", prompt);
  if (options?.model) {
    formData.append("model", options.model);
  }
  if (options?.size) {
    formData.append("size", options.size);
  }
  formData.append("n", "1");

  return httpRequest<{ created: number; data: ImageResultItem[] }>(
    "/v1/images/edits",
    {
      method: "POST",
      body: formData,
    },
  );
}

export async function fetchSettingsConfig() {
  return httpRequest<SettingsResponse>("/api/settings");
}

export async function updateSettingsConfig(settings: SettingsConfig) {
  return httpRequest<SettingsResponse>("/api/settings", {
    method: "POST",
    body: settings,
  });
}

export async function fetchDataStats() {
  return httpRequest<{ stats: DataStats }>("/api/data/stats");
}

export async function runDataCleanup() {
  return httpRequest<{ result: DataCleanupResult }>("/api/data/cleanup", {
    method: "POST",
  });
}

export async function fetchAuthSession() {
  return httpRequest<{ version: string; session: AuthSession }>("/auth/session");
}

export async function listApiKeys() {
  return httpRequest<{ items: APIKeyItem[] }>("/api/admin/keys");
}

export async function createApiKey(payload: {
  name?: string;
  allowed_models?: string[];
  scopes?: string[];
  expires_at?: string | null;
  max_requests?: number | null;
  max_image_count?: number | null;
}) {
  return httpRequest<{ item: APIKeyItem; plain_text: string }>("/api/admin/keys", {
    method: "POST",
    body: payload,
  });
}

export async function updateApiKey(
  keyId: string,
  payload: {
    name?: string;
    enabled?: boolean;
    allowed_models?: string[];
    scopes?: string[];
    expires_at?: string | null;
    max_requests?: number | null;
    max_image_count?: number | null;
  },
) {
  return httpRequest<{ item: APIKeyItem }>(`/api/admin/keys/${keyId}`, {
    method: "POST",
    body: payload,
  });
}

export async function rotateApiKey(keyId: string) {
  return httpRequest<{ item: APIKeyItem; plain_text: string }>(`/api/admin/keys/${keyId}/rotate`, {
    method: "POST",
  });
}

export async function deleteApiKey(keyId: string) {
  return httpRequest<{ ok: boolean }>(`/api/admin/keys/${keyId}`, {
    method: "DELETE",
  });
}

export async function uploadPlaceholderImage(file: File) {
  const formData = new FormData();
  formData.append("image", file);
  return httpRequest<{ placeholder_path: string; config: SettingsConfig }>("/api/admin/image-placeholder", {
    method: "POST",
    body: formData,
  });
}

export async function fetchAsyncJobs(params?: {
  limit?: number;
  offset?: number;
  status?: string;
  type?: string;
  query?: string;
  sort?: string;
  order?: string;
  include_hidden?: boolean;
}) {
  const query = new URLSearchParams();
  if (params?.limit) {
    query.set("limit", String(params.limit));
  }
  if (params?.offset) {
    query.set("offset", String(params.offset));
  }
  if (params?.status && params.status !== "all") {
    query.set("status", params.status);
  }
  if (params?.type && params.type !== "all") {
    query.set("type", params.type);
  }
  if (params?.query?.trim()) {
    query.set("query", params.query.trim());
  }
  if (params?.sort) {
    query.set("sort", params.sort);
  }
  if (params?.order) {
    query.set("order", params.order);
  }
  if (typeof params?.include_hidden === "boolean") {
    query.set("include_hidden", String(params.include_hidden));
  }
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return httpRequest<PaginatedAsyncJobsResponse>(`/api/async/jobs${suffix}`);
}

export async function fetchGalleryJobs(params?: {
  limit?: number;
  offset?: number;
  query?: string;
  sort?: string;
  order?: string;
  include_hidden?: boolean;
}) {
  const query = new URLSearchParams();
  if (params?.limit) {
    query.set("limit", String(params.limit));
  }
  if (params?.offset) {
    query.set("offset", String(params.offset));
  }
  if (params?.query?.trim()) {
    query.set("query", params.query.trim());
  }
  if (params?.sort) {
    query.set("sort", params.sort);
  }
  if (params?.order) {
    query.set("order", params.order);
  }
  if (typeof params?.include_hidden === "boolean") {
    query.set("include_hidden", String(params.include_hidden));
  }
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return httpRequest<PaginatedGalleryResponse>(`/api/gallery${suffix}`);
}

export async function fetchWaterfallImages(params?: {
  limit?: number;
  offset?: number;
  query?: string;
  include_blocked?: boolean;
  sort?: string;
  order?: string;
  include_hidden?: boolean;
}) {
  const query = new URLSearchParams();
  if (params?.limit) {
    query.set("limit", String(params.limit));
  }
  if (params?.offset) {
    query.set("offset", String(params.offset));
  }
  if (params?.query?.trim()) {
    query.set("query", params.query.trim());
  }
  if (typeof params?.include_blocked === "boolean") {
    query.set("include_blocked", String(params.include_blocked));
  }
  if (params?.sort) {
    query.set("sort", params.sort);
  }
  if (params?.order) {
    query.set("order", params.order);
  }
  if (typeof params?.include_hidden === "boolean") {
    query.set("include_hidden", String(params.include_hidden));
  }
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return httpRequest<PaginatedWaterfallResponse>(`/api/gallery/wall${suffix}`);
}

export async function updateGalleryImageState(
  jobId: string,
  imageIndex: number,
  payload: {
    is_recommended?: boolean | null;
    is_pinned?: boolean | null;
    is_blocked?: boolean | null;
  },
) {
  return httpRequest<{ item: PreviewImageItem }>(`/api/gallery/images/${jobId}/${imageIndex}`, {
    method: "POST",
    body: payload,
  });
}

export async function fetchAsyncJob(jobId: string) {
  return httpRequest<{ job: AsyncJobItem }>(`/api/async/jobs/${jobId}`);
}

export async function fetchAsyncJobResult(jobId: string) {
  return httpRequest<{ job: AsyncJobItem; result: unknown }>(`/api/async/jobs/${jobId}/result`);
}

export async function fetchAsyncJobLog(jobId: string) {
  return httpRequest<{ job: AsyncJobItem; log_path?: string | null; log_text: string }>(`/api/async/jobs/${jobId}/log`);
}

export async function createAsyncJob(payload: {
  type: AsyncJobType | string;
  payload: Record<string, unknown>;
}) {
  return httpRequest<{ job: AsyncJobItem }>("/api/async/jobs", {
    method: "POST",
    body: payload,
  });
}

export async function streamAsyncJobEvents(
  jobId: string,
  handlers: {
    onEvent?: (event: string, payload: unknown) => void;
    signal?: AbortSignal;
  } = {},
) {
  const authKey = await getStoredAuthKey();
  const baseUrl = webConfig.apiUrl.replace(/\/$/, "");
  const response = await fetch(`${baseUrl}/api/async/jobs/${jobId}/events`, {
    headers: {
      Accept: "text/event-stream",
      ...(authKey ? { Authorization: `Bearer ${authKey}` } : {}),
    },
    signal: handlers.signal,
  });
  if (!response.ok || !response.body) {
    const message = await response.text();
    throw new Error(message || `SSE 订阅失败 (${response.status})`);
  }

  const decoder = new TextDecoder("utf-8");
  const reader = response.body.getReader();
  let buffer = "";

  const emitEvent = (chunk: string) => {
    const lines = chunk
      .split(/\r?\n/)
      .map((line) => line.trimEnd())
      .filter(Boolean);
    if (lines.length === 0) {
      return;
    }
    let eventName = "message";
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim() || "message";
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }
    const rawPayload = dataLines.join("\n");
    if (!rawPayload) {
      return;
    }
    if (rawPayload === "[DONE]") {
      handlers.onEvent?.("done", rawPayload);
      return;
    }
    try {
      handlers.onEvent?.(eventName, JSON.parse(rawPayload));
    } catch {
      handlers.onEvent?.(eventName, rawPayload);
    }
  };

  while (true) {
    let chunk: ReadableStreamReadResult<Uint8Array>;
    try {
      chunk = await reader.read();
    } catch (error) {
      throw new Error(error instanceof Error ? error.message : "SSE 连接已中断");
    }
    if (chunk.done) {
      break;
    }
    buffer += decoder.decode(chunk.value, { stream: true });
    const chunks = buffer.split(/\r?\n\r?\n/);
    buffer = chunks.pop() || "";
    chunks.forEach(emitEvent);
  }

  const rest = buffer.trim();
  if (rest) {
    emitEvent(rest);
  }
}

// ── CPA (CLIProxyAPI) ──────────────────────────────────────────────

export type CPAPool = {
  id: string;
  name: string;
  base_url: string;
  import_job?: CPAImportJob | null;
};

export type CPARemoteFile = {
  name: string;
  email: string;
};

export type CPAImportJob = {
  job_id: string;
  status: "pending" | "running" | "completed" | "failed";
  created_at: string;
  updated_at: string;
  total: number;
  completed: number;
  added: number;
  skipped: number;
  refreshed: number;
  failed: number;
  errors: Array<{ name: string; error: string }>;
};

export async function fetchCPAPools() {
  return httpRequest<{ pools: CPAPool[] }>("/api/cpa/pools");
}

export async function createCPAPool(pool: { name: string; base_url: string; secret_key: string }) {
  return httpRequest<{ pool: CPAPool; pools: CPAPool[] }>("/api/cpa/pools", {
    method: "POST",
    body: pool,
  });
}

export async function updateCPAPool(
  poolId: string,
  updates: { name?: string; base_url?: string; secret_key?: string },
) {
  return httpRequest<{ pool: CPAPool; pools: CPAPool[] }>(`/api/cpa/pools/${poolId}`, {
    method: "POST",
    body: updates,
  });
}

export async function deleteCPAPool(poolId: string) {
  return httpRequest<{ pools: CPAPool[] }>(`/api/cpa/pools/${poolId}`, {
    method: "DELETE",
  });
}

export async function fetchCPAPoolFiles(poolId: string) {
  return httpRequest<{ pool_id: string; files: CPARemoteFile[] }>(`/api/cpa/pools/${poolId}/files`);
}

export async function startCPAImport(poolId: string, names: string[]) {
  return httpRequest<{ import_job: CPAImportJob | null }>(`/api/cpa/pools/${poolId}/import`, {
    method: "POST",
    body: { names },
  });
}

export async function fetchCPAPoolImportJob(poolId: string) {
  return httpRequest<{ import_job: CPAImportJob | null }>(`/api/cpa/pools/${poolId}/import`);
}

// ── Sub2API ────────────────────────────────────────────────────────

export type Sub2APIServer = {
  id: string;
  name: string;
  base_url: string;
  email: string;
  has_api_key: boolean;
  group_id: string;
  import_job?: CPAImportJob | null;
};

export type Sub2APIRemoteAccount = {
  id: string;
  name: string;
  email: string;
  plan_type: string;
  status: string;
  expires_at: string;
  has_refresh_token: boolean;
};

export type Sub2APIRemoteGroup = {
  id: string;
  name: string;
  description: string;
  platform: string;
  status: string;
  account_count: number;
  active_account_count: number;
};

export async function fetchSub2APIServers() {
  return httpRequest<{ servers: Sub2APIServer[] }>("/api/sub2api/servers");
}

export async function createSub2APIServer(server: {
  name: string;
  base_url: string;
  email: string;
  password: string;
  api_key: string;
  group_id: string;
}) {
  return httpRequest<{ server: Sub2APIServer; servers: Sub2APIServer[] }>("/api/sub2api/servers", {
    method: "POST",
    body: server,
  });
}

export async function updateSub2APIServer(
  serverId: string,
  updates: {
    name?: string;
    base_url?: string;
    email?: string;
    password?: string;
    api_key?: string;
    group_id?: string;
  },
) {
  return httpRequest<{ server: Sub2APIServer; servers: Sub2APIServer[] }>(`/api/sub2api/servers/${serverId}`, {
    method: "POST",
    body: updates,
  });
}

export async function fetchSub2APIServerGroups(serverId: string) {
  return httpRequest<{ server_id: string; groups: Sub2APIRemoteGroup[] }>(
    `/api/sub2api/servers/${serverId}/groups`,
  );
}

export async function deleteSub2APIServer(serverId: string) {
  return httpRequest<{ servers: Sub2APIServer[] }>(`/api/sub2api/servers/${serverId}`, {
    method: "DELETE",
  });
}

export async function fetchSub2APIServerAccounts(serverId: string) {
  return httpRequest<{ server_id: string; accounts: Sub2APIRemoteAccount[] }>(
    `/api/sub2api/servers/${serverId}/accounts`,
  );
}

export async function startSub2APIImport(serverId: string, accountIds: string[]) {
  return httpRequest<{ import_job: CPAImportJob | null }>(`/api/sub2api/servers/${serverId}/import`, {
    method: "POST",
    body: { account_ids: accountIds },
  });
}

export async function fetchSub2APIImportJob(serverId: string) {
  return httpRequest<{ import_job: CPAImportJob | null }>(`/api/sub2api/servers/${serverId}/import`);
}

// ── Upstream proxy ────────────────────────────────────────────────

export type ProxySettings = {
  enabled: boolean;
  url: string;
};

export type ProxyTestResult = {
  ok: boolean;
  status: number;
  latency_ms: number;
  error: string | null;
};

export async function fetchProxy() {
  return httpRequest<{ proxy: ProxySettings }>("/api/proxy");
}

export async function updateProxy(updates: { enabled?: boolean; url?: string }) {
  return httpRequest<{ proxy: ProxySettings }>("/api/proxy", {
    method: "POST",
    body: updates,
  });
}

export async function testProxy(url?: string) {
  return httpRequest<{ result: ProxyTestResult }>("/api/proxy/test", {
    method: "POST",
    body: { url: url ?? "" },
  });
}
