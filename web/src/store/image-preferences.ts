"use client";

import localforage from "localforage";

import type { ImageConversationMode, ImageRequestMode } from "@/store/image-conversations";

export type ImagePreferences = {
  imageModel: string;
  requestMode: ImageRequestMode;
  imageCount: string;
  imageSizePreset: string;
  customImageSize: string;
  imageMode: ImageConversationMode;
};

export const DEFAULT_IMAGE_PREFERENCES: ImagePreferences = {
  imageModel: "auto",
  requestMode: "async_sse",
  imageCount: "1",
  imageSizePreset: "1:1",
  customImageSize: "",
  imageMode: "generate",
};

const IMAGE_PREFERENCES_KEY = "chatgpt2api_image_preferences";

const imagePreferenceStorage = localforage.createInstance({
  name: "chatgpt2api",
  storeName: "image_preferences",
});

function normalizePreferences(value: unknown): ImagePreferences {
  if (!value || typeof value !== "object") {
    return DEFAULT_IMAGE_PREFERENCES;
  }
  const candidate = value as Record<string, unknown>;
  return {
    imageModel: String(candidate.imageModel || DEFAULT_IMAGE_PREFERENCES.imageModel).trim() || "auto",
    requestMode: "async_sse",
    imageCount: String(candidate.imageCount || DEFAULT_IMAGE_PREFERENCES.imageCount).trim() || "1",
    imageSizePreset:
      String(candidate.imageSizePreset || DEFAULT_IMAGE_PREFERENCES.imageSizePreset).trim() || "1:1",
    customImageSize: String(candidate.customImageSize || "").trim(),
    imageMode: candidate.imageMode === "edit" ? "edit" : "generate",
  };
}

export async function getStoredImagePreferences() {
  if (typeof window === "undefined") {
    return DEFAULT_IMAGE_PREFERENCES;
  }
  return normalizePreferences(await imagePreferenceStorage.getItem<ImagePreferences>(IMAGE_PREFERENCES_KEY));
}

export async function setStoredImagePreferences(preferences: ImagePreferences) {
  if (typeof window === "undefined") {
    return;
  }
  await imagePreferenceStorage.setItem(IMAGE_PREFERENCES_KEY, normalizePreferences(preferences));
}
