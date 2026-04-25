"use client";

import { Database, LoaderCircle, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { fetchDataStats, runDataCleanup, type DataStats } from "@/lib/api";

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let current = value;
  let index = 0;
  while (current >= 1024 && index < units.length - 1) {
    current /= 1024;
    index += 1;
  }
  return `${current >= 10 || index === 0 ? current.toFixed(0) : current.toFixed(1)} ${units[index]}`;
}

function formatTime(value?: string) {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

const categoryLabels: Record<string, string> = {
  system_logs: "系统日志",
  task_logs: "任务日志",
  images: "图片文件",
  jobs: "任务元数据",
  job_results: "任务结果",
  placeholders: "占位图",
  other: "其他文件",
};

export function DataStorageCard() {
  const [stats, setStats] = useState<DataStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRunningCleanup, setIsRunningCleanup] = useState(false);
  const [lastCleanupAt, setLastCleanupAt] = useState<string>("");

  const loadStats = useCallback(async (silent = false) => {
    if (!silent) {
      setIsLoading(true);
    }
    try {
      const data = await fetchDataStats();
      setStats(data.stats);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "读取 data 目录统计失败");
    } finally {
      if (!silent) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  const handleCleanup = async () => {
    setIsRunningCleanup(true);
    try {
      const data = await runDataCleanup();
      setStats(data.result.stats);
      setLastCleanupAt(String(data.result.run_at || ""));
      toast.success("已执行 data 清理");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "执行 data 清理失败");
    } finally {
      setIsRunningCleanup(false);
    }
  };

  return (
    <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
      <CardContent className="space-y-5 p-6">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold tracking-tight">Data 存储概览</h2>
            <p className="text-sm text-stone-500">
              查看 `data` 目录尺寸、文件分类统计，并支持立刻执行一次图片与日志清理。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {stats ? (
              <Badge variant="info" className="rounded-full px-3 py-1 text-xs">
                最近统计 {formatTime(stats.generated_at)}
              </Badge>
            ) : null}
            {lastCleanupAt ? (
              <Badge variant="success" className="rounded-full px-3 py-1 text-xs">
                最近清理 {formatTime(lastCleanupAt)}
              </Badge>
            ) : null}
          </div>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-10">
            <LoaderCircle className="size-5 animate-spin text-stone-400" />
          </div>
        ) : (
          <>
            <div className="grid gap-4 md:grid-cols-3">
              <div className="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-4">
                <div className="mb-2 flex items-center gap-2 text-sm text-stone-500">
                  <Database className="size-4" />
                  data 根目录
                </div>
                <div className="truncate text-sm text-stone-700">{stats?.root || "—"}</div>
              </div>
              <div className="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-4">
                <div className="text-sm text-stone-500">总文件数</div>
                <div className="mt-2 text-2xl font-semibold tracking-tight text-stone-900">
                  {stats?.total_files ?? 0}
                </div>
              </div>
              <div className="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-4">
                <div className="text-sm text-stone-500">总占用</div>
                <div className="mt-2 text-2xl font-semibold tracking-tight text-stone-900">
                  {formatBytes(stats?.total_bytes ?? 0)}
                </div>
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
              {Object.entries(stats?.categories || {}).map(([key, value]) => (
                <div key={key} className="rounded-2xl border border-stone-200 bg-white px-4 py-4">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <div className="text-sm font-medium text-stone-800">{categoryLabels[key] || key}</div>
                    <div className="text-xs text-stone-500">{value.files} 个文件</div>
                  </div>
                  <div className="text-lg font-semibold tracking-tight text-stone-900">{formatBytes(value.bytes)}</div>
                  <div className="mt-2 truncate text-xs text-stone-500">{value.path}</div>
                </div>
              ))}
            </div>
          </>
        )}

        <div className="flex flex-wrap justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            className="h-10 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
            onClick={() => void loadStats(true)}
            disabled={isLoading || isRunningCleanup}
          >
            {isLoading ? <LoaderCircle className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
            刷新统计
          </Button>
          <Button
            type="button"
            className="h-10 rounded-xl bg-stone-950 px-4 text-white hover:bg-stone-800"
            onClick={() => void handleCleanup()}
            disabled={isRunningCleanup}
          >
            {isRunningCleanup ? <LoaderCircle className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
            立即清理
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
