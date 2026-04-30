"use client";

import { FileText, Images, LoaderCircle, RefreshCw, Wrench } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  applyHistoryRecovery,
  fetchImageManagement,
  fetchSystemLogTail,
  scanHistoryRecovery,
  type HistoryRecoveryReport,
  type ImageManagementResponse,
  type SystemLogTail,
} from "@/lib/api";

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

function candidateTotal(report: HistoryRecoveryReport | null) {
  if (!report) {
    return 0;
  }
  return report.candidates.async_jobs + report.candidates.gallery_images + report.candidates.task_logs;
}

export function MaintenanceCard() {
  const [logTail, setLogTail] = useState<SystemLogTail | null>(null);
  const [images, setImages] = useState<ImageManagementResponse | null>(null);
  const [report, setReport] = useState<HistoryRecoveryReport | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isScanning, setIsScanning] = useState(false);
  const [isApplying, setIsApplying] = useState(false);

  const loadOverview = useCallback(async (silent = false) => {
    if (!silent) {
      setIsLoading(true);
    }
    try {
      const [logResponse, imageResponse] = await Promise.all([
        fetchSystemLogTail(160),
        fetchImageManagement(18),
      ]);
      setLogTail(logResponse.log);
      setImages(imageResponse.images);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载维护信息失败");
    } finally {
      if (!silent) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  const handleScan = async () => {
    setIsScanning(true);
    try {
      const response = await scanHistoryRecovery();
      setReport(response.report);
      toast.success(`扫描完成：发现 ${candidateTotal(response.report)} 条可补记录`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "扫描历史失败");
    } finally {
      setIsScanning(false);
    }
  };

  const handleApply = async () => {
    setIsApplying(true);
    try {
      const response = await applyHistoryRecovery();
      setReport(response.result.after);
      await loadOverview(true);
      const inserted = response.result.inserted;
      toast.success(
        `重建完成：任务 ${inserted.async_jobs}，图片 ${inserted.gallery_images}，日志 ${inserted.task_logs}`,
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "执行重建修复失败");
    } finally {
      setIsApplying(false);
    }
  };

  return (
    <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
      <CardContent className="space-y-5 p-6">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold tracking-tight">日志、图片管理与重建修复</h2>
            <p className="text-sm text-stone-500">
              这里可以查看 system.log、最近图片文件，并从历史图片/日志/job 文件补回任务、画廊和瀑布墙记录。
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            className="h-10 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
            onClick={() => void loadOverview(true)}
            disabled={isLoading}
          >
            {isLoading ? <LoaderCircle className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
            刷新概览
          </Button>
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <section className="space-y-3 rounded-2xl border border-stone-200 bg-stone-50/70 p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm font-medium text-stone-800">
                <FileText className="size-4" />
                日志管理
              </div>
              <Badge variant={logTail?.exists ? "success" : "secondary"}>
                {logTail?.exists ? formatBytes(logTail.bytes) : "未创建"}
              </Badge>
            </div>
            <div className="truncate text-xs text-stone-500">{logTail?.path || "—"}</div>
            <pre className="max-h-[260px] overflow-auto whitespace-pre-wrap break-words rounded-xl bg-stone-950 px-3 py-3 text-[11px] leading-5 text-stone-100">
              <code>{logTail?.lines?.length ? logTail.lines.join("\n") : "当前暂无 system.log 内容。"}</code>
            </pre>
          </section>

          <section className="space-y-3 rounded-2xl border border-stone-200 bg-stone-50/70 p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm font-medium text-stone-800">
                <Images className="size-4" />
                图片管理
              </div>
              <Badge variant="info">{images?.total_originals ?? 0} 张原图</Badge>
            </div>
            <div className="truncate text-xs text-stone-500">{images?.root || "—"}</div>
            <div className="grid grid-cols-3 gap-2">
              {(images?.items || []).slice(0, 9).map((item) => (
                <a
                  key={item.relative_path}
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="group overflow-hidden rounded-xl border border-stone-200 bg-white"
                  title={`${item.relative_path} · ${formatTime(item.modified_at)}`}
                >
                  <img
                    src={item.thumbnail_url || item.url}
                    alt={item.relative_path}
                    className="aspect-square w-full object-cover transition group-hover:opacity-90"
                  />
                </a>
              ))}
            </div>
            <div className="text-xs leading-5 text-stone-500">
              总图片文件 {images?.total_files ?? 0} 个；这里只显示最近 {images?.items.length ?? 0} 张，完整历史请在画廊/瀑布墙调高每页数量。
            </div>
          </section>

          <section className="space-y-3 rounded-2xl border border-stone-200 bg-stone-50/70 p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm font-medium text-stone-800">
                <Wrench className="size-4" />
                重建修复
              </div>
              <Badge variant={candidateTotal(report) > 0 ? "warning" : "secondary"}>
                可补 {candidateTotal(report)}
              </Badge>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-xl bg-white px-3 py-3 text-center">
                <div className="text-xs text-stone-500">任务</div>
                <div className="mt-1 text-xl font-semibold text-stone-900">{report?.candidates.async_jobs ?? "—"}</div>
              </div>
              <div className="rounded-xl bg-white px-3 py-3 text-center">
                <div className="text-xs text-stone-500">图片</div>
                <div className="mt-1 text-xl font-semibold text-stone-900">{report?.candidates.gallery_images ?? "—"}</div>
              </div>
              <div className="rounded-xl bg-white px-3 py-3 text-center">
                <div className="text-xs text-stone-500">日志</div>
                <div className="mt-1 text-xl font-semibold text-stone-900">{report?.candidates.task_logs ?? "—"}</div>
              </div>
            </div>
            {report ? (
              <div className="rounded-xl bg-white px-3 py-3 text-xs leading-5 text-stone-500">
                当前库内：任务 {report.existing.async_jobs}，图片 {report.existing.gallery_images}，日志 {report.existing.task_logs}。
                扫描原图 {report.source_counts.image_original_files || 0} 个，日志事件 {report.source_counts.system_log_events || 0} 条。
              </div>
            ) : (
              <div className="rounded-xl bg-white px-3 py-3 text-xs leading-5 text-stone-500">
                先点“扫描可恢复记录”做 dry-run；确认后再执行修复。修复只新增缺失记录，不删除、不覆盖置顶/推荐/禁止状态。
              </div>
            )}
            <div className="flex flex-wrap justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                className="h-10 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                onClick={() => void handleScan()}
                disabled={isScanning || isApplying}
              >
                {isScanning ? <LoaderCircle className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
                扫描可恢复记录
              </Button>
              <Button
                type="button"
                className="h-10 rounded-xl bg-stone-950 px-4 text-white hover:bg-stone-800"
                onClick={() => void handleApply()}
                disabled={isApplying || isScanning}
              >
                {isApplying ? <LoaderCircle className="size-4 animate-spin" /> : <Wrench className="size-4" />}
                执行重建修复
              </Button>
            </div>
          </section>
        </div>
      </CardContent>
    </Card>
  );
}
