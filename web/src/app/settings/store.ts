"use client";

import { create } from "zustand";
import { toast } from "sonner";

import {
  createCPAPool,
  deleteCPAPool,
  fetchCPAPoolFiles,
  fetchCPAPools,
  fetchSettingsConfig,
  startCPAImport,
  updateCPAPool,
  updateSettingsConfig,
  type CPAPool,
  type CPARemoteFile,
  type SettingsConfig,
} from "@/lib/api";

export const PAGE_SIZE_OPTIONS = ["50", "100", "200"] as const;

export type PageSizeOption = (typeof PAGE_SIZE_OPTIONS)[number];

function normalizeConfig(config: SettingsConfig): SettingsConfig {
  return {
    ...config,
    "auth-key": typeof config["auth-key"] === "string" ? config["auth-key"] : "",
    port: Number(config.port || 80),
    refresh_account_interval_minute: Number(config.refresh_account_interval_minute || 5),
    proxy: typeof config.proxy === "string" ? config.proxy : "",
    base_url: typeof config.base_url === "string" ? config.base_url : "",
    image_failure_strategy:
      typeof config.image_failure_strategy === "string" ? config.image_failure_strategy : "fail",
    image_retry_count: Number(config.image_retry_count || 0),
    image_parallel_attempts: Number(config.image_parallel_attempts || 1),
    image_placeholder_path: typeof config.image_placeholder_path === "string" ? config.image_placeholder_path : "",
    image_response_format:
      typeof config.image_response_format === "string" ? config.image_response_format : "b64_json",
    image_thumbnail_max_size: Number(config.image_thumbnail_max_size || 512),
    image_thumbnail_quality: Number(config.image_thumbnail_quality || 85),
    image_wall_thumbnail_max_size: Number(config.image_wall_thumbnail_max_size || 960),
    image_retention_days: Number(config.image_retention_days || 7),
    task_log_retention_days: Number(config.task_log_retention_days || 7),
    system_log_max_mb: Number(config.system_log_max_mb || 32),
    data_cleanup_enabled: Boolean(config.data_cleanup_enabled),
    data_cleanup_interval_minutes: Number(config.data_cleanup_interval_minutes || 60),
  };
}

function normalizeFiles(items: CPARemoteFile[]) {
  const seen = new Set<string>();
  const files: CPARemoteFile[] = [];
  for (const item of items) {
    const name = String(item.name || "").trim();
    if (!name || seen.has(name)) {
      continue;
    }
    seen.add(name);
    files.push({
      name,
      email: String(item.email || "").trim(),
    });
  }
  return files;
}

type SettingsStore = {
  config: SettingsConfig | null;
  isLoadingConfig: boolean;
  isSavingConfig: boolean;

  pools: CPAPool[];
  isLoadingPools: boolean;
  deletingId: string | null;
  loadingFilesId: string | null;

  dialogOpen: boolean;
  editingPool: CPAPool | null;
  formName: string;
  formBaseUrl: string;
  formSecretKey: string;
  showSecret: boolean;
  isSavingPool: boolean;

  browserOpen: boolean;
  browserPool: CPAPool | null;
  remoteFiles: CPARemoteFile[];
  selectedNames: string[];
  fileQuery: string;
  filePage: number;
  pageSize: PageSizeOption;
  isStartingImport: boolean;

  initialize: () => Promise<void>;
  loadConfig: () => Promise<void>;
  saveConfig: () => Promise<void>;
  setAuthKey: (value: string) => void;
  setRefreshAccountIntervalMinute: (value: string) => void;
  setProxy: (value: string) => void;
  setBaseUrl: (value: string) => void;
  setPort: (value: string) => void;
  setImageFailureStrategy: (value: string) => void;
  setImageRetryCount: (value: string) => void;
  setImageParallelAttempts: (value: string) => void;
  setImagePlaceholderPath: (value: string) => void;
  setImageResponseFormat: (value: string) => void;
  setImageThumbnailMaxSize: (value: string) => void;
  setImageThumbnailQuality: (value: string) => void;
  setImageWallThumbnailMaxSize: (value: string) => void;
  setImageRetentionDays: (value: string) => void;
  setTaskLogRetentionDays: (value: string) => void;
  setSystemLogMaxMb: (value: string) => void;
  setDataCleanupEnabled: (value: boolean) => void;
  setDataCleanupIntervalMinutes: (value: string) => void;

  loadPools: (silent?: boolean) => Promise<void>;
  openAddDialog: () => void;
  openEditDialog: (pool: CPAPool) => void;
  setDialogOpen: (open: boolean) => void;
  setFormName: (value: string) => void;
  setFormBaseUrl: (value: string) => void;
  setFormSecretKey: (value: string) => void;
  setShowSecret: (checked: boolean) => void;
  savePool: () => Promise<void>;
  deletePool: (pool: CPAPool) => Promise<void>;

  browseFiles: (pool: CPAPool) => Promise<void>;
  setBrowserOpen: (open: boolean) => void;
  toggleFile: (name: string, checked: boolean) => void;
  replaceSelectedNames: (names: string[]) => void;
  setFileQuery: (value: string) => void;
  setFilePage: (page: number) => void;
  setPageSize: (value: PageSizeOption) => void;
  startImport: () => Promise<void>;
};

export const useSettingsStore = create<SettingsStore>((set, get) => ({
  config: null,
  isLoadingConfig: true,
  isSavingConfig: false,

  pools: [],
  isLoadingPools: true,
  deletingId: null,
  loadingFilesId: null,

  dialogOpen: false,
  editingPool: null,
  formName: "",
  formBaseUrl: "",
  formSecretKey: "",
  showSecret: false,
  isSavingPool: false,

  browserOpen: false,
  browserPool: null,
  remoteFiles: [],
  selectedNames: [],
  fileQuery: "",
  filePage: 1,
  pageSize: "100",
  isStartingImport: false,

  initialize: async () => {
    await Promise.allSettled([get().loadConfig(), get().loadPools()]);
  },

  loadConfig: async () => {
    set({ isLoadingConfig: true });
    try {
      const data = await fetchSettingsConfig();
      set({
        config: normalizeConfig(data.config),
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载系统配置失败");
    } finally {
      set({ isLoadingConfig: false });
    }
  },

  saveConfig: async () => {
    const { config } = get();
    if (!config) {
      return;
    }

    set({ isSavingConfig: true });
    try {
      const data = await updateSettingsConfig({
        ...config,
        "auth-key": String(config["auth-key"] || "").trim(),
        port: Math.max(1, Math.min(65535, Number(config.port) || 80)),
        refresh_account_interval_minute: Math.max(1, Number(config.refresh_account_interval_minute) || 1),
        proxy: config.proxy.trim(),
        base_url: String(config.base_url || "").trim(),
        image_failure_strategy: String(config.image_failure_strategy || "fail").trim() || "fail",
        image_retry_count: Math.max(0, Math.min(5, Number(config.image_retry_count) || 0)),
        image_parallel_attempts: Math.max(1, Math.min(8, Number(config.image_parallel_attempts) || 1)),
        image_placeholder_path: String(config.image_placeholder_path || "").trim(),
        image_response_format: String(config.image_response_format || "b64_json").trim() || "b64_json",
        image_thumbnail_max_size: Math.max(64, Math.min(2048, Number(config.image_thumbnail_max_size) || 512)),
        image_thumbnail_quality: Math.max(1, Math.min(100, Number(config.image_thumbnail_quality) || 85)),
        image_wall_thumbnail_max_size: Math.max(128, Math.min(4096, Number(config.image_wall_thumbnail_max_size) || 960)),
        image_retention_days: Math.max(0, Math.min(365, Number(config.image_retention_days) || 0)),
        task_log_retention_days: Math.max(0, Math.min(365, Number(config.task_log_retention_days) || 0)),
        system_log_max_mb: Math.max(1, Math.min(1024, Number(config.system_log_max_mb) || 1)),
        data_cleanup_enabled: Boolean(config.data_cleanup_enabled),
        data_cleanup_interval_minutes: Math.max(1, Math.min(1440, Number(config.data_cleanup_interval_minutes) || 1)),
      });
      set({
        config: normalizeConfig(data.config),
      });
      toast.success("配置已保存");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存系统配置失败");
    } finally {
      set({ isSavingConfig: false });
    }
  },

  setAuthKey: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          "auth-key": value,
        },
      };
    });
  },

  setRefreshAccountIntervalMinute: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          refresh_account_interval_minute: value,
        },
      };
    });
  },

  setPort: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          port: value,
        },
      };
    });
  },

  setProxy: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          proxy: value,
        },
      };
    });
  },

  setBaseUrl: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          base_url: value,
        },
      };
    });
  },

  setImageFailureStrategy: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          image_failure_strategy: value,
        },
      };
    });
  },

  setImageRetryCount: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          image_retry_count: value,
        },
      };
    });
  },

  setImageParallelAttempts: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          image_parallel_attempts: value,
        },
      };
    });
  },

  setImagePlaceholderPath: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          image_placeholder_path: value,
        },
      };
    });
  },

  setImageResponseFormat: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          image_response_format: value,
        },
      };
    });
  },

  setImageThumbnailMaxSize: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          image_thumbnail_max_size: value,
        },
      };
    });
  },

  setImageThumbnailQuality: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          image_thumbnail_quality: value,
        },
      };
    });
  },

  setImageWallThumbnailMaxSize: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          image_wall_thumbnail_max_size: value,
        },
      };
    });
  },

  setImageRetentionDays: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          image_retention_days: value,
        },
      };
    });
  },

  setTaskLogRetentionDays: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          task_log_retention_days: value,
        },
      };
    });
  },

  setSystemLogMaxMb: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          system_log_max_mb: value,
        },
      };
    });
  },

  setDataCleanupEnabled: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          data_cleanup_enabled: value,
        },
      };
    });
  },

  setDataCleanupIntervalMinutes: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          data_cleanup_interval_minutes: value,
        },
      };
    });
  },

  loadPools: async (silent = false) => {
    if (!silent) {
      set({ isLoadingPools: true });
    }
    try {
      const data = await fetchCPAPools();
      set({ pools: data.pools });
    } catch (error) {
      if (!silent) {
        toast.error(error instanceof Error ? error.message : "加载 CPA 连接失败");
      }
    } finally {
      if (!silent) {
        set({ isLoadingPools: false });
      }
    }
  },

  openAddDialog: () => {
    set({
      editingPool: null,
      formName: "",
      formBaseUrl: "",
      formSecretKey: "",
      showSecret: false,
      dialogOpen: true,
    });
  },

  openEditDialog: (pool) => {
    set({
      editingPool: pool,
      formName: pool.name,
      formBaseUrl: pool.base_url,
      formSecretKey: "",
      showSecret: false,
      dialogOpen: true,
    });
  },

  setDialogOpen: (open) => {
    set({ dialogOpen: open });
  },

  setFormName: (value) => {
    set({ formName: value });
  },

  setFormBaseUrl: (value) => {
    set({ formBaseUrl: value });
  },

  setFormSecretKey: (value) => {
    set({ formSecretKey: value });
  },

  setShowSecret: (checked) => {
    set({ showSecret: checked });
  },

  savePool: async () => {
    const { editingPool, formName, formBaseUrl, formSecretKey } = get();
    if (!formBaseUrl.trim()) {
      toast.error("请输入 CPA 地址");
      return;
    }
    if (!editingPool && !formSecretKey.trim()) {
      toast.error("请输入 Secret Key");
      return;
    }

    set({ isSavingPool: true });
    try {
      if (editingPool) {
        const data = await updateCPAPool(editingPool.id, {
          name: formName.trim(),
          base_url: formBaseUrl.trim(),
          secret_key: formSecretKey.trim() || undefined,
        });
        set({ pools: data.pools, dialogOpen: false });
        toast.success("连接已更新");
      } else {
        const data = await createCPAPool({
          name: formName.trim(),
          base_url: formBaseUrl.trim(),
          secret_key: formSecretKey.trim(),
        });
        set({ pools: data.pools, dialogOpen: false });
        toast.success("连接已添加");
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    } finally {
      set({ isSavingPool: false });
    }
  },

  deletePool: async (pool) => {
    set({ deletingId: pool.id });
    try {
      const data = await deleteCPAPool(pool.id);
      set({ pools: data.pools });
      toast.success("连接已删除");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "删除失败");
    } finally {
      set({ deletingId: null });
    }
  },

  browseFiles: async (pool) => {
    set({ loadingFilesId: pool.id });
    try {
      const data = await fetchCPAPoolFiles(pool.id);
      const files = normalizeFiles(data.files);
      set({
        browserPool: pool,
        remoteFiles: files,
        selectedNames: [],
        fileQuery: "",
        filePage: 1,
        browserOpen: true,
      });
      toast.success(`读取成功，共 ${files.length} 个远程账号`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "读取远程账号失败");
    } finally {
      set({ loadingFilesId: null });
    }
  },

  setBrowserOpen: (open) => {
    set({ browserOpen: open });
  },

  toggleFile: (name, checked) => {
    set((state) => {
      if (checked) {
        return {
          selectedNames: Array.from(new Set([...state.selectedNames, name])),
        };
      }
      return {
        selectedNames: state.selectedNames.filter((item) => item !== name),
      };
    });
  },

  replaceSelectedNames: (names) => {
    set({ selectedNames: Array.from(new Set(names)) });
  },

  setFileQuery: (value) => {
    set({ fileQuery: value, filePage: 1 });
  },

  setFilePage: (page) => {
    set({ filePage: page });
  },

  setPageSize: (value) => {
    set({ pageSize: value, filePage: 1 });
  },

  startImport: async () => {
    const { browserPool, selectedNames, pools } = get();
    if (!browserPool) {
      return;
    }
    if (selectedNames.length === 0) {
      toast.error("请先选择要导入的账号");
      return;
    }

    set({ isStartingImport: true });
    try {
      const result = await startCPAImport(browserPool.id, selectedNames);
      set({
        pools: pools.map((pool) =>
          pool.id === browserPool.id ? { ...pool, import_job: result.import_job } : pool,
        ),
        browserOpen: false,
      });
      toast.success("导入任务已启动");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "启动导入失败");
    } finally {
      set({ isStartingImport: false });
    }
  },
}));
