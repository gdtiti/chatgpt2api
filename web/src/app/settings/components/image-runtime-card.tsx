"use client";

import { ImageUp, LoaderCircle, Save } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { uploadPlaceholderImage } from "@/lib/api";

import { useSettingsStore } from "../store";

const FAILURE_STRATEGIES = [
  { value: "fail", label: "直接失败", description: "上游失败后原样返回错误。" },
  { value: "retry", label: "自动重试", description: "按重试次数再次请求上游。" },
  { value: "placeholder", label: "占位图", description: "失败后返回后台配置的占位图片。" },
] as const;

export function ImageRuntimeCard() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploadingPlaceholder, setIsUploadingPlaceholder] = useState(false);
  const config = useSettingsStore((state) => state.config);
  const isLoadingConfig = useSettingsStore((state) => state.isLoadingConfig);
  const isSavingConfig = useSettingsStore((state) => state.isSavingConfig);
  const loadConfig = useSettingsStore((state) => state.loadConfig);
  const saveConfig = useSettingsStore((state) => state.saveConfig);
  const setImageFailureStrategy = useSettingsStore((state) => state.setImageFailureStrategy);
  const setImageRetryCount = useSettingsStore((state) => state.setImageRetryCount);
  const setImageParallelAttempts = useSettingsStore((state) => state.setImageParallelAttempts);
  const setImagePlaceholderPath = useSettingsStore((state) => state.setImagePlaceholderPath);
  const setImageResponseFormat = useSettingsStore((state) => state.setImageResponseFormat);
  const setImageRetentionDays = useSettingsStore((state) => state.setImageRetentionDays);
  const setTaskLogRetentionDays = useSettingsStore((state) => state.setTaskLogRetentionDays);
  const setSystemLogMaxMb = useSettingsStore((state) => state.setSystemLogMaxMb);
  const setDataCleanupEnabled = useSettingsStore((state) => state.setDataCleanupEnabled);
  const setDataCleanupIntervalMinutes = useSettingsStore((state) => state.setDataCleanupIntervalMinutes);

  const handleUploadPlaceholder = async (file?: File) => {
    if (!file) {
      return;
    }
    setIsUploadingPlaceholder(true);
    try {
      const data = await uploadPlaceholderImage(file);
      await loadConfig();
      toast.success(`占位图已更新：${data.placeholder_path}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "上传占位图失败");
    } finally {
      setIsUploadingPlaceholder(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  if (isLoadingConfig) {
    return (
      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="flex items-center justify-center p-10">
          <LoaderCircle className="size-5 animate-spin text-stone-400" />
        </CardContent>
      </Card>
    );
  }

  const strategy = String(config?.image_failure_strategy || "fail");
  const currentStrategy = FAILURE_STRATEGIES.find((item) => item.value === strategy) || FAILURE_STRATEGIES[0];

  return (
    <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
      <CardContent className="space-y-5 p-6">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold tracking-tight">图片运行策略</h2>
            <p className="text-sm text-stone-500">
              控制图片失败兜底、首个成功返回、图片落盘返回格式，以及 `/data` 下图片与日志的自动清理策略。
            </p>
          </div>
          <Badge variant="info" className="rounded-full px-3 py-1 text-xs">
            前端默认固定异步 SSE
          </Badge>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(event) => {
            void handleUploadPlaceholder(event.target.files?.[0]);
          }}
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-2">
            <label className="text-sm text-stone-700">失败策略</label>
            <Select value={strategy} onValueChange={setImageFailureStrategy}>
              <SelectTrigger className="h-10 rounded-xl border-stone-200 bg-white">
                <SelectValue placeholder="选择失败策略" />
              </SelectTrigger>
              <SelectContent>
                {FAILURE_STRATEGIES.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-stone-500">{currentStrategy.description}</p>
          </div>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">并发尝试数</label>
            <Input
              value={String(config?.image_parallel_attempts || "")}
              onChange={(event) => setImageParallelAttempts(event.target.value)}
              placeholder="1-8"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">一次请求可并发多个上游尝试，最先成功的结果会被返回。</p>
          </div>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">重试次数</label>
            <Input
              value={String(config?.image_retry_count || "")}
              onChange={(event) => setImageRetryCount(event.target.value)}
              placeholder="0-5"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">仅在失败策略为“自动重试”时生效。</p>
          </div>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">占位图路径</label>
            <Input
              value={String(config?.image_placeholder_path || "")}
              onChange={(event) => setImagePlaceholderPath(event.target.value)}
              placeholder="data/placeholders/image-placeholder.png"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">支持手动填写，或直接上传图片由后台自动落盘并回写路径。</p>
          </div>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">图片返回格式</label>
            <Select value={String(config?.image_response_format || "b64_json")} onValueChange={setImageResponseFormat}>
              <SelectTrigger className="h-10 rounded-xl border-stone-200 bg-white">
                <SelectValue placeholder="选择返回格式" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="b64_json">b64_json</SelectItem>
                <SelectItem value="url">url</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-stone-500">设置为 `url` 后，图片将保存到 `/data/日期/任务ID-序号.扩展名`；未配置外链时返回 `/api/view/data/...`，配置了外链时自动拼接完整 URL。</p>
          </div>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">图片保留天数</label>
            <Input
              value={String(config?.image_retention_days ?? "")}
              onChange={(event) => setImageRetentionDays(event.target.value)}
              placeholder="7"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">超过保留期的落盘图片会在自动清理时删除。填 `0` 表示不按天数删除。</p>
          </div>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">任务日志保留天数</label>
            <Input
              value={String(config?.task_log_retention_days ?? "")}
              onChange={(event) => setTaskLogRetentionDays(event.target.value)}
              placeholder="7"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">任务日志位于 `data/task_logs`，超过保留期会自动清理。</p>
          </div>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">系统日志最大体积（MB）</label>
            <Input
              value={String(config?.system_log_max_mb ?? "")}
              onChange={(event) => setSystemLogMaxMb(event.target.value)}
              placeholder="32"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">超过上限后会自动截断 `data/system.log`，保留最新内容。</p>
          </div>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">自动清理间隔（分钟）</label>
            <Input
              value={String(config?.data_cleanup_interval_minutes ?? "")}
              onChange={(event) => setDataCleanupIntervalMinutes(event.target.value)}
              placeholder="60"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">后台守护线程会按该周期执行一次自动清理。</p>
          </div>
        </div>

        <label className="flex items-start gap-3 rounded-2xl border border-stone-200 bg-stone-50 px-4 py-4">
          <Checkbox
            checked={Boolean(config?.data_cleanup_enabled)}
            onCheckedChange={(checked) => setDataCleanupEnabled(Boolean(checked))}
            className="mt-0.5"
          />
          <span className="space-y-1">
            <span className="block text-sm font-medium text-stone-800">启用自动清理</span>
            <span className="block text-xs leading-6 text-stone-500">
              开启后会按照上面的保留策略自动清理图片和任务日志，并控制系统日志体积。
            </span>
          </span>
        </label>

        <div className="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="space-y-1">
              <div className="text-sm font-medium text-stone-800">占位图上传</div>
              <p className="text-xs leading-6 text-stone-500">
                当失败策略为占位图时，会返回这里上传的图片。环境变量仍会覆盖配置文件中的同名项。
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              className="h-10 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
              disabled={isUploadingPlaceholder}
              onClick={() => fileInputRef.current?.click()}
            >
              {isUploadingPlaceholder ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : (
                <ImageUp className="size-4" />
              )}
              上传占位图
            </Button>
          </div>
        </div>

        <div className="flex justify-end">
          <Button
            className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
            onClick={() => void saveConfig()}
            disabled={isSavingConfig}
          >
            {isSavingConfig ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
            保存
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
