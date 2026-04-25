import webConfig from "@/constants/common-env";
import { getStoredAuthKey, type AuthSession } from "@/store/auth";

import { httpRequest } from "@/lib/request";

export type { AuthSession };

export type AccountType = "Free" | "Plus" | "ProLite" | "Pro" | "Team";
export type AccountStatus = "正常" | "限流" | "异常" | "禁用";
export type ImageModel = "auto" | "gpt-image-1" | "gpt-image-2" | "codex-gpt-image-2" | string;
export type ImageSizeOption = "1:1" | "16:9" | "9:16" | "4:3" | "3:4";
export type ImageSizeValue = string;

export const IMAGE_SIZE_OPTIONS: ImageSizeOption[] = ["1:1", "16:9", "9:16", "4:3", "3:4"];

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
  "auth-key"?: string;
  port?: number | string;
  refresh_account_interval_minute?: number | string;
  image_failure_strategy?: "fail" | "retry" | "placeholder" | string;
  image_retry_count?: number | string;
  image_parallel_attempts?: number | string;
  image_placeholder_path?: string;
  [key: string]: unknown;
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
    supports_multiple_reference_images?: boolean;
  } | null;
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
  prompt_preview?: string | null;
  requested_count?: number;
  size?: string | null;
  input_image_count?: number;
  result_ready?: boolean;
  result_count?: number;
  error?: { message?: string } | null;
};

export type AsyncJobSummary = {
  total: number;
  queued: number;
  running: number;
  succeeded: number;
  failed: number;
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

export async function generateImage(prompt: string, options?: { model?: ImageModel; size?: ImageSizeValue }) {
  return httpRequest<{ created: number; data: Array<{ b64_json: string; revised_prompt?: string }> }>(
    "/v1/images/generations",
    {
      method: "POST",
      body: {
        prompt,
        ...(options?.model ? { model: options.model } : {}),
        ...(options?.size ? { size: options.size } : {}),
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

  return httpRequest<{ created: number; data: Array<{ b64_json: string; revised_prompt?: string }> }>(
    "/v1/images/edits",
    {
      method: "POST",
      body: formData,
    },
  );
}

export async function fetchSettingsConfig() {
  return httpRequest<{ config: SettingsConfig }>("/api/settings");
}

export async function updateSettingsConfig(settings: SettingsConfig) {
  return httpRequest<{ config: SettingsConfig }>("/api/settings", {
    method: "POST",
    body: settings,
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
  status?: string;
  type?: string;
}) {
  const query = new URLSearchParams();
  if (params?.limit) {
    query.set("limit", String(params.limit));
  }
  if (params?.status && params.status !== "all") {
    query.set("status", params.status);
  }
  if (params?.type && params.type !== "all") {
    query.set("type", params.type);
  }
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return httpRequest<{ items: AsyncJobItem[]; summary: AsyncJobSummary }>(`/api/async/jobs${suffix}`);
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
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
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
