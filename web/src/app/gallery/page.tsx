"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Images, LoaderCircle, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { ImageLightbox } from "@/components/image-lightbox";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { fetchAsyncJobs, type AsyncJobItem, type PreviewImageItem } from "@/lib/api";

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
  }).format(date);
}

function galleryItemsFromJob(job: AsyncJobItem): PreviewImageItem[] {
  if (!Array.isArray(job.preview_images)) {
    return [];
  }
  return job.preview_images.filter((item) => typeof item?.src === "string" && item.src.trim().length > 0);
}

export default function GalleryPage() {
  const didLoadRef = useRef(false);
  const [jobs, setJobs] = useState<AsyncJobItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [lightboxItems, setLightboxItems] = useState<Array<{ id: string; src: string }>>([]);
  const [lightboxIndex, setLightboxIndex] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);

  const galleryJobs = useMemo(
    () =>
      jobs.filter((job) => job.status === "succeeded" && galleryItemsFromJob(job).length > 0),
    [jobs],
  );

  const loadJobs = async (silent = false) => {
    if (!silent) {
      setIsLoading(true);
    }
    try {
      const response = await fetchAsyncJobs({ limit: 200 });
      setJobs(response.items);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载画廊失败");
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

  return (
    <>
      <section className="space-y-6 pb-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-2">
            <div className="text-xs font-semibold tracking-[0.18em] text-stone-500 uppercase">Gallery</div>
            <h1 className="text-2xl font-semibold tracking-tight">画廊</h1>
            <p className="max-w-[920px] text-sm leading-7 text-stone-500">按任务查看已生成图片，左侧显示提示词，右侧显示缩略图，点击可查看原图。</p>
          </div>
          <Button
            type="button"
            variant="outline"
            className="h-10 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
            onClick={() => void loadJobs()}
            disabled={isLoading}
          >
            {isLoading ? <LoaderCircle className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
            刷新画廊
          </Button>
        </div>

        <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
          <CardContent className="space-y-4 p-6">
            {isLoading ? (
              <div className="flex items-center justify-center py-14">
                <LoaderCircle className="size-5 animate-spin text-stone-400" />
              </div>
            ) : galleryJobs.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
                <div className="rounded-xl bg-stone-100 p-3 text-stone-500">
                  <Images className="size-5" />
                </div>
                <div className="space-y-1">
                  <p className="text-sm font-medium text-stone-700">还没有可展示的图片</p>
                  <p className="text-sm text-stone-500">完成文生图、图生图或带图片输出的 responses 任务后，会在这里出现。</p>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {galleryJobs.map((job) => {
                  const images = galleryItemsFromJob(job);
                  const lightboxGroup = images.map((item, index) => ({
                    id: item.id || `${job.id}-${index}`,
                    src: item.url || item.src,
                  }));
                  return (
                    <div key={job.id} className="grid gap-4 rounded-2xl border border-stone-200 bg-stone-50/70 p-4 lg:grid-cols-[280px_minmax(0,1fr)]">
                      <div className="space-y-2">
                        <div className="text-[11px] uppercase tracking-[0.18em] text-stone-400">{job.type}</div>
                        <div className="text-sm font-medium leading-6 text-stone-800">{job.prompt_preview || "—"}</div>
                        <div className="text-xs text-stone-500">
                          {job.model || "auto"} · {formatTime(job.updated_at)} · {job.result_count || images.length} 张
                        </div>
                        <code className="block break-all text-[11px] text-stone-400">{job.id}</code>
                      </div>
                      <div className="flex flex-wrap gap-3">
                        {images.map((item, index) => (
                          <div key={item.id || `${job.id}-${index}`} className="space-y-2">
                            <button
                              type="button"
                              className="overflow-hidden rounded-xl border border-stone-200 bg-white"
                              onClick={() => {
                                setLightboxItems(lightboxGroup);
                                setLightboxIndex(index);
                                setLightboxOpen(true);
                              }}
                            >
                              <img
                                src={item.src}
                                alt={`任务 ${job.id} 缩略图 ${index + 1}`}
                                className="h-28 w-28 object-cover"
                              />
                            </button>
                            {item.url ? (
                              <a
                                href={item.url}
                                target="_blank"
                                rel="noreferrer"
                                className="block w-28 truncate text-center text-[11px] text-stone-500 hover:text-stone-800"
                              >
                                查看原图
                              </a>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      <ImageLightbox
        images={lightboxItems}
        currentIndex={lightboxIndex}
        open={lightboxOpen}
        onOpenChange={setLightboxOpen}
        onIndexChange={setLightboxIndex}
      />
    </>
  );
}
