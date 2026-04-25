"use client";

import localforage from "localforage";

export const AUTH_KEY_STORAGE_KEY = "chatgpt2api_auth_key";
export const AUTH_SESSION_STORAGE_KEY = "chatgpt2api_auth_session";

export type AuthSession = {
  key_id: string;
  name: string;
  kind: "admin" | "client";
  is_admin: boolean;
  scopes: string[];
  allowed_models: string[];
  request_count: number;
  max_requests?: number | null;
  remaining_requests?: number | null;
  image_count: number;
  max_image_count?: number | null;
  remaining_image_count?: number | null;
};

const authStorage = localforage.createInstance({
  name: "chatgpt2api",
  storeName: "auth",
});

function normalizeStringArray(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => String(item || "").trim()).filter(Boolean);
}

function normalizeOptionalNumber(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeAuthSession(value: unknown): AuthSession | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const candidate = value as Record<string, unknown>;
  const keyId = String(candidate.key_id || "").trim();
  const kind = candidate.kind === "client" ? "client" : "admin";
  if (!keyId) {
    return null;
  }
  return {
    key_id: keyId,
    name: String(candidate.name || keyId).trim() || keyId,
    kind,
    is_admin: candidate.is_admin === true || kind === "admin",
    scopes: normalizeStringArray(candidate.scopes),
    allowed_models: normalizeStringArray(candidate.allowed_models),
    request_count: Math.max(0, Number(candidate.request_count) || 0),
    max_requests: normalizeOptionalNumber(candidate.max_requests),
    remaining_requests: normalizeOptionalNumber(candidate.remaining_requests),
    image_count: Math.max(0, Number(candidate.image_count) || 0),
    max_image_count: normalizeOptionalNumber(candidate.max_image_count),
    remaining_image_count: normalizeOptionalNumber(candidate.remaining_image_count),
  };
}

export async function getStoredAuthKey() {
  if (typeof window === "undefined") {
    return "";
  }
  const value = await authStorage.getItem<string>(AUTH_KEY_STORAGE_KEY);
  return String(value || "").trim();
}

export async function setStoredAuthKey(authKey: string) {
  const normalizedAuthKey = String(authKey || "").trim();
  if (!normalizedAuthKey) {
    await clearStoredAuthKey();
    return;
  }
  await authStorage.setItem(AUTH_KEY_STORAGE_KEY, normalizedAuthKey);
}

export async function clearStoredAuthKey() {
  if (typeof window === "undefined") {
    return;
  }
  await authStorage.removeItem(AUTH_KEY_STORAGE_KEY);
  await authStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
}

export async function getStoredAuthSession() {
  if (typeof window === "undefined") {
    return null;
  }
  return normalizeAuthSession(await authStorage.getItem<AuthSession>(AUTH_SESSION_STORAGE_KEY));
}

export async function setStoredAuthSession(session: AuthSession | null) {
  if (typeof window === "undefined") {
    return;
  }
  const normalizedSession = normalizeAuthSession(session);
  if (!normalizedSession) {
    await authStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
    return;
  }
  await authStorage.setItem(AUTH_SESSION_STORAGE_KEY, normalizedSession);
}

export async function clearStoredAuthSession() {
  if (typeof window === "undefined") {
    return;
  }
  await authStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
}
