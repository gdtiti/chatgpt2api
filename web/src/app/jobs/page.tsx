"use client";

import { useEffect, useMemo, useRef, useState, type ComponentProps } from "react";
import {
  CheckCircle2,
  ChevronRight,
  Clock3,
  Copy,
  FileText,
  Image as ImageIcon,
  ListFilter,
  LoaderCircle,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { ImageLightbox } from "@/components/image-lightbox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  fetchAsyncJob,
  fetchAsyncJobLog,
  fetchAsyncJobResult,
  fetchAsyncJobs,
  type AsyncJobItem,
  type AsyncJobStatus,
  type AsyncJobSummary,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const statusOptions: Array<{ value: AsyncJobStatus | "all"; label: string }> = [
  { value: "all", label: "全部状态" },
  { value: "queued", label: "排队中" },
  { value: "running", label: "执行中" },
  { value: "succeeded", label: "已成功" },
  { value: "failed", label: "已失败" },
];

const typeOptions = [
  { value: "all", label: "全部类型" },
  { value: "chat.completions", label: "Chat" },
  { value: "responses", label: "Responses" },
  { value: "images.generations", label: "文生图" },
  { value: "images.edits", label: "图生图" },
] as const;

const statusMeta: Record<
  AsyncJobStatus,
  {
    label: string;
    badge: ComponentProps<typeof Badge>["variant"];
    icon: typeof Clock3;
  }
> = {
  queued: { label: "排队中", badge: "warning", icon: Clock3 },
  running: { label: "执行中", badge: "info", icon: RefreshCw },
  succeeded: { label: "已成功", badge: "success", icon: CheckCircle2 },
  failed: { label: "已失败", badge: "danger", icon: XCircle },
};

type DetailTab = "result" | "log";

function formatJobType(value: string) {
  const matched = typeOptions.find((item) => item.value === value);
  return matched?.label || value;
}

function formatTime(value?: string | null) {
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

function formatError(job: AsyncJobItem) {
  return String(job.error?.message || "").trim() || "—";
}

function formatPrompt(job: AsyncJobItem) {
  return String(job.prompt_preview || "").trim() || "—";
}

function formatJson(value: unknown) {
  if (value === null || value === undefined) {
    return "当前暂无结果。";
  }
  return JSON.stringify(value, null, 2);
}

function extractImageSources(result: unknown) {
  if (!result || typeof result !== "object" || !Array.isArray((result as { data?: unknown[] }).data)) {
    return [];
  }
  return (result as { data: Array<Record<string, unknown>> }).data.flatMap((item, index) => {
    const b64Json = typeof item.b64_json === "string" ? item.b64_json.trim() : "";
    if (b64Json) {
      return [{ id: `image-${index}`, src: `data:image/png;base64,${b64Json}` }];
    }
    const imageUrl = typeof item.url === "string" ? item.url.trim() : "";
    if (imageUrl) {
      return [{ id: `image-${index}`, src: imageUrl }];
    }
    return [];
  });
}

export default function JobsPage() {
  const didLoadRef = useRef(false);
  const [jobs, setJobs] = useState<AsyncJobItem[]>([]);
  const [summary, setSummary] = useState<AsyncJobSummary>({
    total: 0,
    queued: 0,
    running: 0,
    succeeded: 0,
    failed: 0,
  });
  const [statusFilter, setStatusFilter] = useState<AsyncJobStatus | "all">("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [limit, setLimit] = useState("50");
  const [isLoading, setIsLoading] = useState(true);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailJob, setDetailJob] = useState<AsyncJobItem | null>(null);
  const [detailResult, setDetailResult] = useState<unknown>(null);
  const [detailLog, setDetailLog] = useState("");
  const [detailLogPath, setDetailLogPath] = useState<string | null>(null);
  const [detailTab, setDetailTab] = useState<DetailTab>("result");
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [lightboxImages, setLightboxImages] = useState<Array<{ id: string; src: string }>>([]);
  const [lightboxIndex, setLightboxIndex] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);

  const hasActiveJobs = useMemo(
    () => jobs.some((job) => job.status === "queued" || job.status === "running"),
    [jobs],
  );
  const detailImages = useMemo(() => extractImageSources(detailResult), [detailResult]);

  const loadJobs = async (silent = false) => {
    if (!silent) {
      setIsLoading(true);
    }
    try {
      const data = await fetchAsyncJobs({
        limit: Number(limit) || 50,
        status: statusFilter,
        type: typeFilter,
      });
      setJobs(data.items);
      setSummary(data.summary);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载任务列表失败");
    } finally {
      if (!silent) {
        setIsLoading(false);
      }
    }
  };

  useEffect(() => {
    if (didLoadRef.current) {
      return;
    }
    didLoadRef.current = true;
    void loadJobs();
  }, []);

  useEffect(() => {
    if (!didLoadRef.current) {
      return;
    }
    void loadJobs();
  }, [limit, statusFilter, typeFilter]);

  useEffect(() => {
    if (!hasActiveJobs) {
      return;
    }
    const timer = window.setInterval(() => {
      void loadJobs(true);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [hasActiveJobs, limit, statusFilter, typeFilter]);

  const handleOpenDetail = async (job: AsyncJobItem) => {
    setDetailOpen(true);
    setDetailJob(job);
    setDetailResult(null);
    setDetailLog("");
    setDetailLogPath(job.log_path || null);
    setDetailTab(job.status === "succeeded" ? "result" : "log");
    setIsLoadingDetail(true);
    try {
      const [logResponse, detailResponse] = await Promise.allSettled([
        fetchAsyncJobLog(job.id),
        job.status === "succeeded" ? fetchAsyncJobResult(job.id) : fetchAsyncJob(job.id),
      ]);

      if (logResponse.status === "fulfilled") {
        setDetailLog(logResponse.value.log_text || "");
        setDetailLogPath(logResponse.value.log_path || logResponse.value.job.log_path || null);
        setDetailJob(logResponse.value.job);
      }

      if (detailResponse.status === "fulfilled") {
        if ("result" in detailResponse.value) {
          setDetailJob(detailResponse.value.job);
          setDetailResult(detailResponse.value.result);
        } else {
          setDetailJob(detailResponse.value.job);
        }
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载任务详情失败");
    } finally {
      setIsLoadingDetail(false);
    }
  };

  const metricCards = [
    { key: "total", label: "任务总数", value: summary.total, color: "text-stone-900", icon: ListFilter },
    { key: "queued", label: "排队中", value: summary.queued, color: "text-amber-600", icon: Clock3 },
    { key: "running", label: "执行中", value: summary.running, color: "text-sky-600", icon: RefreshCw },
    { key: "succeeded", label: "已成功", value: summary.succeeded, color: "text-emerald-600", icon: CheckCircle2 },
    { key: "failed", label: "已失败", value: summary.failed, color: "text-rose-600", icon: XCircle },
  ] as const;

  return (
    <>
      <section className="space-y-6 pb-8">
        <div className="space-y-2">
          <div className="text-xs font-semibold tracking-[0.18em] text-stone-500 uppercase">Jobs</div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">任务列表</h1>
            {hasActiveJobs ? (
              <Badge variant="info" className="rounded-full px-3 py-1">
                自动刷新中
              </Badge>
            ) : null}
          </div>
          <p className="max-w-[920px] text-sm leading-7 text-stone-500">
            用于追踪异步任务的排队、执行、成功和失败情况。图片任务在详情里优先展示结果图，日志独立放在日志 tab。
          </p>
        </div>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          {metricCards.map((item) => {
            const Icon = item.icon;
            return (
              <Card key={item.key} className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
                <CardContent className="flex items-start justify-between gap-3 p-5">
                  <div className="space-y-1">
                    <div className="text-sm text-stone-500">{item.label}</div>
                    <div className={cn("text-2xl font-semibold tracking-tight", item.color)}>{item.value}</div>
                  </div>
                  <div className="rounded-xl bg-stone-100 p-2 text-stone-500">
                    <Icon className={cn("size-5", item.key === "running" && summary.running > 0 ? "animate-spin" : "")} />
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </section>

        <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
          <CardContent className="space-y-5 p-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-wrap items-center gap-3">
                <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as AsyncJobStatus | "all")}>
                  <SelectTrigger className="h-10 w-[160px] rounded-xl border-stone-200 bg-white">
                    <SelectValue placeholder="状态" />
                  </SelectTrigger>
                  <SelectContent>
                    {statusOptions.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Select value={typeFilter} onValueChange={setTypeFilter}>
                  <SelectTrigger className="h-10 w-[180px] rounded-xl border-stone-200 bg-white">
                    <SelectValue placeholder="任务类型" />
                  </SelectTrigger>
                  <SelectContent>
                    {typeOptions.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Select value={limit} onValueChange={setLimit}>
                  <SelectTrigger className="h-10 w-[120px] rounded-xl border-stone-200 bg-white">
                    <SelectValue placeholder="数量" />
                  </SelectTrigger>
                  <SelectContent>
                    {["20", "50", "100", "200"].map((item) => (
                      <SelectItem key={item} value={item}>
                        {item} 条
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <Button
                type="button"
                variant="outline"
                className="h-10 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                onClick={() => void loadJobs()}
                disabled={isLoading}
              >
                {isLoading ? <LoaderCircle className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
                刷新任务
              </Button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[1180px] text-left">
                <thead className="border-b border-stone-100 text-[11px] uppercase tracking-[0.18em] text-stone-400">
                  <tr>
                    <th className="px-4 py-3">任务 ID</th>
                    <th className="px-4 py-3">状态</th>
                    <th className="px-4 py-3">类型</th>
                    <th className="px-4 py-3">模型</th>
                    <th className="px-4 py-3">请求摘要</th>
                    <th className="px-4 py-3">参数</th>
                    <th className="px-4 py-3">调用方</th>
                    <th className="px-4 py-3">更新时间</th>
                    <th className="px-4 py-3">错误</th>
                    <th className="px-4 py-3">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => {
                    const meta = statusMeta[(job.status as AsyncJobStatus) || "queued"] || statusMeta.queued;
                    const StatusIcon = meta.icon;
                    const inputMeta = [
                      job.size ? `比例 ${job.size}` : "",
                      job.requested_count ? `数量 ${job.requested_count}` : "",
                      job.input_image_count ? `参考图 ${job.input_image_count}` : "",
                      job.result_ready ? `结果 ${job.result_count || 0}` : "",
                    ].filter(Boolean);

                    return (
                      <tr
                        key={job.id}
                        className="border-b border-stone-100/80 text-sm text-stone-600 transition-colors hover:bg-stone-50/70"
                      >
                        <td className="px-4 py-4">
                          <div className="flex items-center gap-2">
                            <code className="max-w-[180px] truncate rounded-md bg-stone-100 px-2 py-1 text-xs text-stone-700">
                              {job.id}
                            </code>
                            <button
                              type="button"
                              className="rounded-lg p-1 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
                              onClick={() => {
                                void navigator.clipboard.writeText(job.id);
                                toast.success("任务 ID 已复制");
                              }}
                            >
                              <Copy className="size-4" />
                            </button>
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <Badge variant={meta.badge} className="inline-flex items-center gap-1 rounded-md px-2 py-1">
                            <StatusIcon className={cn("size-3.5", job.status === "running" ? "animate-spin" : "")} />
                            {meta.label}
                          </Badge>
                        </td>
                        <td className="px-4 py-4">
                          <Badge variant="secondary" className="rounded-md bg-stone-100 text-stone-700">
                            {formatJobType(job.type)}
                          </Badge>
                        </td>
                        <td className="px-4 py-4 text-stone-700">{job.model || "—"}</td>
                        <td className="px-4 py-4">
                          <div className="max-w-[260px] space-y-1">
                            <div className="line-clamp-2 text-sm text-stone-700">{formatPrompt(job)}</div>
                            <div className="text-xs text-stone-400">创建于 {formatTime(job.created_at)}</div>
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <div className="flex max-w-[220px] flex-wrap gap-1.5">
                            {inputMeta.length > 0 ? (
                              inputMeta.map((item) => (
                                <Badge key={item} variant="outline" className="rounded-full">
                                  {item}
                                </Badge>
                              ))
                            ) : (
                              <span className="text-xs text-stone-400">—</span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <div className="max-w-[150px] space-y-1 text-xs text-stone-500">
                            <div className="font-medium text-stone-700">{job.api_key_name || "admin"}</div>
                            <div className="truncate">{job.api_key_id || "—"}</div>
                          </div>
                        </td>
                        <td className="px-4 py-4 text-xs leading-5 text-stone-500">
                          <div>{formatTime(job.updated_at)}</div>
                        </td>
                        <td className="px-4 py-4">
                          <div className="max-w-[180px] line-clamp-2 text-xs leading-5 text-rose-600">
                            {formatError(job)}
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <Button
                            type="button"
                            variant="outline"
                            className="h-9 rounded-xl border-stone-200 bg-white px-3 text-stone-700"
                            onClick={() => void handleOpenDetail(job)}
                          >
                            {job.status === "succeeded" ? <ImageIcon className="size-4" /> : <ChevronRight className="size-4" />}
                            {job.status === "succeeded" ? "查看结果" : "查看详情"}
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {!isLoading && jobs.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
                  <div className="rounded-xl bg-stone-100 p-3 text-stone-500">
                    <ListFilter className="size-5" />
                  </div>
                  <div className="space-y-1">
                    <p className="text-sm font-medium text-stone-700">没有匹配的任务</p>
                    <p className="text-sm text-stone-500">调整筛选条件后再看，或者等待新的异步任务进入队列。</p>
                  </div>
                </div>
              ) : null}
            </div>
          </CardContent>
        </Card>
      </section>

      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="w-[min(92vw,1040px)] max-w-[1040px] rounded-[28px]">
          <DialogHeader>
            <DialogTitle>任务详情</DialogTitle>
            <DialogDescription>查看当前任务状态、结果和日志。</DialogDescription>
          </DialogHeader>

          {isLoadingDetail ? (
            <div className="flex items-center justify-center py-12">
              <LoaderCircle className="size-5 animate-spin text-stone-400" />
            </div>
          ) : detailJob ? (
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-2xl bg-stone-50 px-4 py-3">
                  <div className="text-xs text-stone-400">状态</div>
                  <div className="mt-1 text-sm font-medium text-stone-800">
                    {statusMeta[(detailJob.status as AsyncJobStatus) || "queued"]?.label || detailJob.status}
                  </div>
                </div>
                <div className="rounded-2xl bg-stone-50 px-4 py-3">
                  <div className="text-xs text-stone-400">类型</div>
                  <div className="mt-1 text-sm font-medium text-stone-800">{formatJobType(detailJob.type)}</div>
                </div>
                <div className="rounded-2xl bg-stone-50 px-4 py-3">
                  <div className="text-xs text-stone-400">模型</div>
                  <div className="mt-1 text-sm font-medium text-stone-800">{detailJob.model || "—"}</div>
                </div>
                <div className="rounded-2xl bg-stone-50 px-4 py-3">
                  <div className="text-xs text-stone-400">调用方</div>
                  <div className="mt-1 text-sm font-medium text-stone-800">{detailJob.api_key_name || detailJob.api_key_id || "admin"}</div>
                </div>
              </div>

              <div className="rounded-2xl border border-stone-200 bg-white px-4 py-4">
                <div className="text-sm font-medium text-stone-800">任务信息</div>
                <div className="mt-3 grid gap-3 text-sm text-stone-600 md:grid-cols-2">
                  <div>
                    <span className="text-stone-400">任务 ID：</span>
                    <code className="break-all text-xs text-stone-700">{detailJob.id}</code>
                  </div>
                  <div>
                    <span className="text-stone-400">更新时间：</span>
                    {formatTime(detailJob.updated_at)}
                  </div>
                  <div>
                    <span className="text-stone-400">创建时间：</span>
                    {formatTime(detailJob.created_at)}
                  </div>
                  <div>
                    <span className="text-stone-400">结果条数：</span>
                    {detailJob.result_count || 0}
                  </div>
                  <div>
                    <span className="text-stone-400">请求数量：</span>
                    {detailJob.requested_count || 1}
                  </div>
                  <div>
                    <span className="text-stone-400">参考图数量：</span>
                    {detailJob.input_image_count || 0}
                  </div>
                </div>
                <div className="mt-4 space-y-2">
                  <div className="text-xs text-stone-400">请求摘要</div>
                  <div className="rounded-xl bg-stone-50 px-3 py-3 text-sm leading-6 text-stone-700">
                    {formatPrompt(detailJob)}
                  </div>
                </div>
                {detailJob.error?.message ? (
                  <div className="mt-4 space-y-2">
                    <div className="text-xs text-stone-400">错误信息</div>
                    <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-3 text-sm leading-6 text-rose-700">
                      {detailJob.error.message}
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className={cn(
                    "rounded-full px-4 py-2 text-sm font-medium transition",
                    detailTab === "result" ? "bg-stone-950 text-white" : "bg-stone-100 text-stone-600 hover:bg-stone-200",
                  )}
                  onClick={() => setDetailTab("result")}
                >
                  结果
                </button>
                <button
                  type="button"
                  className={cn(
                    "inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition",
                    detailTab === "log" ? "bg-stone-950 text-white" : "bg-stone-100 text-stone-600 hover:bg-stone-200",
                  )}
                  onClick={() => setDetailTab("log")}
                >
                  <FileText className="size-4" />
                  日志
                </button>
              </div>

              {detailTab === "result" ? (
                <div className="space-y-3">
                  <div className="text-sm font-medium text-stone-800">执行结果</div>
                  {detailImages.length > 0 ? (
                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                      {detailImages.map((image, index) => (
                        <button
                          key={image.id}
                          type="button"
                          className="overflow-hidden rounded-2xl border border-stone-200 bg-stone-50 text-left transition hover:border-stone-300"
                          onClick={() => {
                            setLightboxImages(detailImages);
                            setLightboxIndex(index);
                            setLightboxOpen(true);
                          }}
                        >
                          <img src={image.src} alt={`任务结果 ${index + 1}`} className="aspect-square w-full object-cover" />
                        </button>
                      ))}
                    </div>
                  ) : detailJob.status === "succeeded" ? (
                    <pre className="max-h-[320px] overflow-auto rounded-2xl bg-stone-950 px-4 py-4 text-xs leading-6 text-stone-100">
                      <code>{formatJson(detailResult)}</code>
                    </pre>
                  ) : (
                    <div className="rounded-2xl border border-dashed border-stone-200 bg-stone-50 px-4 py-8 text-sm text-stone-500">
                      当前任务还没有可展示的结果。
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="rounded-2xl border border-stone-200 bg-white px-4 py-4">
                    <div className="text-xs text-stone-400">日志文件</div>
                    <code className="mt-2 block break-all text-xs text-stone-700">{detailLogPath || detailJob.log_path || "—"}</code>
                  </div>
                  <pre className="max-h-[360px] overflow-auto rounded-2xl bg-stone-950 px-4 py-4 text-xs leading-6 text-stone-100">
                    <code>{detailLog || "当前暂无日志内容。"}</code>
                  </pre>
                </div>
              )}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      <ImageLightbox
        images={lightboxImages}
        currentIndex={lightboxIndex}
        open={lightboxOpen}
        onOpenChange={setLightboxOpen}
        onIndexChange={setLightboxIndex}
      />
    </>
  );
}
