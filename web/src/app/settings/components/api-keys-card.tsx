"use client";

import { Copy, KeyRound, LoaderCircle, RefreshCcw, ShieldCheck, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  createApiKey,
  deleteApiKey,
  fetchModelList,
  listApiKeys,
  rotateApiKey,
  updateApiKey,
  type APIKeyItem,
  type ModelItem,
} from "@/lib/api";

function formatTime(value?: string | null) {
  if (!value) {
    return "未使用";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function toDatetimeLocalValue(value?: string | null) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const pad = (input: number) => String(input).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function parseOptionalLimit(value: string) {
  const normalized = value.trim();
  if (!normalized) {
    return null;
  }
  const parsed = Number(normalized);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return Math.floor(parsed);
}

export function APIKeysCard() {
  const [items, setItems] = useState<APIKeyItem[]>([]);
  const [models, setModels] = useState<ModelItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [workingKeyId, setWorkingKeyId] = useState<string | null>(null);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyExpiresAt, setNewKeyExpiresAt] = useState("");
  const [newKeyMaxRequests, setNewKeyMaxRequests] = useState("");
  const [newKeyMaxImageCount, setNewKeyMaxImageCount] = useState("");
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [latestPlainTextKey, setLatestPlainTextKey] = useState<string>("");

  const availableModels = useMemo(() => models.map((item) => item.id).filter(Boolean), [models]);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [keysResult, modelResult] = await Promise.allSettled([listApiKeys(), fetchModelList()]);
      if (keysResult.status === "fulfilled") {
        setItems(keysResult.value.items);
      } else {
        throw keysResult.reason;
      }
      if (modelResult.status === "fulfilled") {
        setModels(modelResult.value.data || []);
      } else {
        setModels([]);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载 API Key 管理数据失败");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const toggleModel = (modelId: string, checked: boolean) => {
    setSelectedModels((current) => {
      if (checked) {
        return Array.from(new Set([...current, modelId]));
      }
      return current.filter((item) => item !== modelId);
    });
  };

  const handleCopy = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(`${label}已复制`);
    } catch {
      toast.error(`复制${label}失败`);
    }
  };

  const handleCreate = async () => {
    setIsCreating(true);
    try {
      const data = await createApiKey({
        name: newKeyName.trim(),
        allowed_models: selectedModels,
        scopes: ["inference"],
        expires_at: newKeyExpiresAt ? new Date(newKeyExpiresAt).toISOString() : null,
        max_requests: parseOptionalLimit(newKeyMaxRequests),
        max_image_count: parseOptionalLimit(newKeyMaxImageCount),
      });
      setItems((current) => [data.item, ...current]);
      setLatestPlainTextKey(data.plain_text);
      setNewKeyName("");
      setNewKeyExpiresAt("");
      setNewKeyMaxRequests("");
      setNewKeyMaxImageCount("");
      setSelectedModels([]);
      toast.success("API Key 已创建");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "创建 API Key 失败");
    } finally {
      setIsCreating(false);
    }
  };

  const handleToggleEnabled = async (item: APIKeyItem, enabled: boolean) => {
    setWorkingKeyId(item.id);
    try {
      const data = await updateApiKey(item.id, { enabled });
      setItems((current) => current.map((key) => (key.id === item.id ? data.item : key)));
      toast.success(enabled ? "API Key 已启用" : "API Key 已停用");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "更新 API Key 状态失败");
    } finally {
      setWorkingKeyId(null);
    }
  };

  const handleRotate = async (item: APIKeyItem, copyAfterRotate = false) => {
    setWorkingKeyId(item.id);
    try {
      const data = await rotateApiKey(item.id);
      setItems((current) => current.map((key) => (key.id === item.id ? data.item : key)));
      setLatestPlainTextKey(data.plain_text);
      if (copyAfterRotate) {
        try {
          await navigator.clipboard.writeText(data.plain_text);
          toast.success(`API Key ${item.name} 已重新生成并复制`);
        } catch {
          toast.warning("新 API Key 已生成，请在上方明文区域手动复制");
        }
      } else {
        toast.success(`API Key ${item.name} 已轮换`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "轮换 API Key 失败");
    } finally {
      setWorkingKeyId(null);
    }
  };

  const handleDelete = async (item: APIKeyItem) => {
    setWorkingKeyId(item.id);
    try {
      await deleteApiKey(item.id);
      setItems((current) => current.filter((key) => key.id !== item.id));
      toast.success(`API Key ${item.name} 已删除`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "删除 API Key 失败");
    } finally {
      setWorkingKeyId(null);
    }
  };

  return (
    <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
      <CardContent className="space-y-6 p-6">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold tracking-tight">API Key 管理</h2>
            <p className="text-sm text-stone-500">
              创建下游调用专用 client key。明文密钥只会在创建或轮换时返回一次。
            </p>
          </div>
          <Badge variant="violet" className="rounded-full px-3 py-1 text-xs">
            `/api/admin/keys`
          </Badge>
        </div>

        {latestPlainTextKey ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div className="space-y-1">
                <div className="text-sm font-medium text-amber-900">最新明文 API Key</div>
                <code className="block break-all text-xs text-amber-800">{latestPlainTextKey}</code>
              </div>
              <Button
                type="button"
                variant="outline"
                className="h-9 rounded-xl border-amber-200 bg-white text-amber-800 hover:bg-amber-100"
                onClick={() => void handleCopy(latestPlainTextKey, "API Key")}
              >
                <Copy className="size-4" />
                复制
              </Button>
            </div>
          </div>
        ) : null}

        <div className="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-4">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm text-stone-700">名称</label>
                <Input
                  value={newKeyName}
                  onChange={(event) => setNewKeyName(event.target.value)}
                  placeholder="例如：ci-runner / mobile-client"
                  className="h-10 rounded-xl border-stone-200 bg-white"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">过期时间</label>
                <Input
                  type="datetime-local"
                  value={newKeyExpiresAt}
                  onChange={(event) => setNewKeyExpiresAt(event.target.value)}
                  className="h-10 rounded-xl border-stone-200 bg-white"
                />
                <p className="text-xs text-stone-500">留空表示长期有效。</p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm text-stone-700">请求次数上限</label>
                  <Input
                    type="number"
                    min="1"
                    step="1"
                    value={newKeyMaxRequests}
                    onChange={(event) => setNewKeyMaxRequests(event.target.value)}
                    placeholder="留空表示不限"
                    className="h-10 rounded-xl border-stone-200 bg-white"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm text-stone-700">图片额度上限</label>
                  <Input
                    type="number"
                    min="1"
                    step="1"
                    value={newKeyMaxImageCount}
                    onChange={(event) => setNewKeyMaxImageCount(event.target.value)}
                    placeholder="留空表示不限"
                    className="h-10 rounded-xl border-stone-200 bg-white"
                  />
                </div>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-sm text-stone-700">允许模型</div>
                <div className="text-xs text-stone-500">不选表示允许全部模型</div>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {availableModels.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-stone-200 bg-white px-3 py-3 text-xs text-stone-500">
                    暂未读取到模型列表。
                  </div>
                ) : (
                  availableModels.map((modelId) => {
                    const checked = selectedModels.includes(modelId);
                    return (
                      <label
                        key={modelId}
                        className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-3 py-3 text-sm text-stone-700"
                      >
                        <Checkbox checked={checked} onCheckedChange={(value) => toggleModel(modelId, value === true)} />
                        <span className="min-w-0 truncate">{modelId}</span>
                      </label>
                    );
                  })
                )}
              </div>
            </div>
          </div>

          <div className="mt-4 flex justify-end">
            <Button
              type="button"
              className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
              disabled={isCreating}
              onClick={() => void handleCreate()}
            >
              {isCreating ? <LoaderCircle className="size-4 animate-spin" /> : <KeyRound className="size-4" />}
              创建 API Key
            </Button>
          </div>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <LoaderCircle className="size-5 animate-spin text-stone-400" />
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-stone-200 bg-stone-50 px-4 py-6 text-sm text-stone-500">
            还没有创建任何 client key。
          </div>
        ) : (
          <div className="space-y-3">
            {items.map((item) => {
              const isWorking = workingKeyId === item.id;
              return (
                <div key={item.id} className="rounded-2xl border border-stone-200 bg-white px-4 py-4">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="space-y-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="text-sm font-semibold text-stone-900">{item.name}</div>
                        <Badge variant={item.enabled ? "success" : "warning"}>{item.enabled ? "启用中" : "已停用"}</Badge>
                        <Badge variant="outline">{item.prefix}</Badge>
                        {item.scopes.map((scope) => (
                          <Badge key={scope} variant="info">
                            {scope}
                          </Badge>
                        ))}
                      </div>
                      <div className="grid gap-2 text-xs leading-6 text-stone-500 sm:grid-cols-2">
                        <div>创建时间：{formatTime(item.created_at)}</div>
                        <div>最近使用：{formatTime(item.last_used_at)}</div>
                        <div>调用次数：{item.request_count}</div>
                        <div>过期时间：{item.expires_at ? formatTime(item.expires_at) : "长期有效"}</div>
                        <div>
                          请求上限：
                          {item.max_requests ? ` ${item.request_count}/${item.max_requests}，剩余 ${item.remaining_requests ?? 0}` : " 不限"}
                        </div>
                        <div>
                          图片额度：
                          {item.max_image_count ? ` ${item.image_count}/${item.max_image_count}，剩余 ${item.remaining_image_count ?? 0}` : " 不限"}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {(item.allowed_models.length > 0 ? item.allowed_models : ["全部模型"]).map((modelId) => (
                          <Badge key={modelId} variant="secondary" className="rounded-full">
                            {modelId}
                          </Badge>
                        ))}
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <label className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-stone-50 px-3 py-2 text-sm text-stone-700">
                        <Checkbox
                          checked={item.enabled}
                          disabled={isWorking}
                          onCheckedChange={(value) => void handleToggleEnabled(item, value === true)}
                        />
                        启用
                      </label>
                      <Button
                        type="button"
                        variant="outline"
                        className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                        disabled={isWorking}
                        onClick={() => void handleRotate(item, true)}
                      >
                        {isWorking ? <LoaderCircle className="size-4 animate-spin" /> : <RefreshCcw className="size-4" />}
                        重新生成并复制
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                        disabled={isWorking}
                        onClick={() => void handleCopy(item.prefix, "Key 前缀")}
                      >
                        <ShieldCheck className="size-4" />
                        复制前缀
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        className="h-9 rounded-xl border-rose-200 bg-white px-4 text-rose-700 hover:bg-rose-50"
                        disabled={isWorking}
                        onClick={() => void handleDelete(item)}
                      >
                        {isWorking ? <LoaderCircle className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
                        删除
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
