"use client";

import { Ban, ChevronLeft, ChevronRight, LoaderCircle, Pin, RefreshCw, Search, Star } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ImageLightbox } from "@/components/image-lightbox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  fetchWaterfallImages,
  updateGalleryImageState,
  type PreviewImageItem,
} from "@/lib/api";
import { cn } from "@/lib/utils";

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

export default function WaterfallPage() {
  const didLoadRef = useRef(false);
  const [items, setItems] = useState<PreviewImageItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [updatingKey, setUpdatingKey] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [limit] = useState(40);
  const [total, setTotal] = useState(0);
  const [queryInput, setQueryInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [includeBlocked, setIncludeBlocked] = useState(false);
  const [lightboxItems, setLightboxItems] = useState<Array<{ id: string; src: string }>>([]);
  const [lightboxIndex, setLightboxIndex] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);

  const pageCount = Math.max(1, Math.ceil(total / limit));

  const loadItems = async (silent = false) => {
    if (!silent) {
      setIsLoading(true);
    }
    try {
      const response = await fetchWaterfallImages({
        limit,
        offset: (page - 1) * limit,
        query: searchQuery,
        include_blocked: includeBlocked,
      });
      setItems(response.items);
      setTotal(response.total);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载瀑布墙失败");
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
    void loadItems();
  }, []);

  useEffect(() => {
    if (!didLoadRef.current) {
      return;
    }
    void loadItems();
  }, [page, searchQuery, includeBlocked]);

  useEffect(() => {
    setPage(1);
  }, [searchQuery, includeBlocked]);

  const patchItem = async (
    item: PreviewImageItem,
    payload: { is_recommended?: boolean; is_pinned?: boolean; is_blocked?: boolean },
  ) => {
    if (!item.job_id || !item.image_index) {
      toast.error("图片缺少数据库索引");
      return;
    }
    const key = `${item.job_id}-${item.image_index}`;
    setUpdatingKey(key);
    try {
      const response = await updateGalleryImageState(item.job_id, item.image_index, payload);
      setItems((current) =>
        current
          .map((candidate) =>
            candidate.job_id === response.item.job_id && candidate.image_index === response.item.image_index
              ? { ...candidate, ...response.item }
              : candidate,
          )
          .filter((candidate) => includeBlocked || !candidate.is_blocked),
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "更新图片状态失败");
    } finally {
      setUpdatingKey(null);
    }
  };

  const lightboxGroup = items.map((item, index) => ({
    id: item.id || `${item.job_id}-${index}`,
    src: item.url || item.wall_url || item.thumbnail_url || item.src,
  }));

  return (
    <>
      <section className="space-y-6 pb-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-2">
            <div className="text-xs font-semibold tracking-[0.18em] text-stone-500 uppercase">Waterfall</div>
            <h1 className="text-2xl font-semibold tracking-tight">瀑布墙</h1>
            <p className="max-w-[920px] text-sm leading-7 text-stone-500">
              使用独立的大预览图展示图库图片。未设置推荐、置顶或禁止时，按最新生成时间从上往下排列。
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            className="h-10 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
            onClick={() => void loadItems()}
            disabled={isLoading}
          >
            {isLoading ? <LoaderCircle className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
            刷新
          </Button>
        </div>

        <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
          <CardContent className="space-y-5 p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  value={queryInput}
                  onChange={(event) => setQueryInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      setSearchQuery(queryInput.trim());
                    }
                  }}
                  placeholder="搜索提示词、模型、任务 ID"
                  className="h-10 w-[260px] rounded-xl border-stone-200 bg-white"
                />
                <Button
                  type="button"
                  variant="outline"
                  className="h-10 rounded-xl border-stone-200 bg-white px-3 text-stone-700"
                  onClick={() => setSearchQuery(queryInput.trim())}
                >
                  <Search className="size-4" />
                  搜索
                </Button>
                <label className="flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-3 py-2 text-sm text-stone-600">
                  <Checkbox checked={includeBlocked} onCheckedChange={(checked) => setIncludeBlocked(Boolean(checked))} />
                  显示禁止项
                </label>
              </div>
              <div className="flex items-center gap-2 text-sm text-stone-500">
                <span>
                  共 {total} 张，第 {page} / {pageCount} 页
                </span>
                <Button
                  type="button"
                  variant="outline"
                  className="h-9 rounded-xl border-stone-200 bg-white px-3 text-stone-700"
                  disabled={isLoading || page <= 1}
                  onClick={() => setPage((value) => Math.max(1, value - 1))}
                >
                  <ChevronLeft className="size-4" />
                  上一页
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="h-9 rounded-xl border-stone-200 bg-white px-3 text-stone-700"
                  disabled={isLoading || page >= pageCount}
                  onClick={() => setPage((value) => Math.min(pageCount, value + 1))}
                >
                  下一页
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            </div>

            {isLoading ? (
              <div className="flex items-center justify-center py-14">
                <LoaderCircle className="size-5 animate-spin text-stone-400" />
              </div>
            ) : items.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-stone-200 bg-stone-50 px-4 py-12 text-center text-sm text-stone-500">
                当前没有可展示的图片。
              </div>
            ) : (
              <div className="columns-1 gap-4 md:columns-2 xl:columns-3 2xl:columns-4">
                {items.map((item, index) => {
                  const imageSrc = item.wall_url || item.thumbnail_url || item.src;
                  const key = `${item.job_id}-${item.image_index}`;
                  const isUpdating = updatingKey === key;
                  return (
                    <article
                      key={key}
                      className={cn(
                        "mb-4 break-inside-avoid overflow-hidden rounded-2xl border bg-white shadow-sm",
                        item.is_blocked ? "border-rose-200 opacity-60" : "border-stone-200",
                      )}
                    >
                      <button
                        type="button"
                        className="block w-full bg-stone-100 text-left"
                        onClick={() => {
                          setLightboxItems(lightboxGroup);
                          setLightboxIndex(index);
                          setLightboxOpen(true);
                        }}
                      >
                        <img src={imageSrc} alt={`瀑布墙图片 ${index + 1}`} className="h-auto w-full object-contain" />
                      </button>
                      <div className="space-y-3 p-3">
                        <div className="flex flex-wrap gap-1.5">
                          {item.is_pinned ? <Badge variant="info">置顶</Badge> : null}
                          {item.is_recommended ? <Badge variant="success">推荐</Badge> : null}
                          {item.is_blocked ? <Badge variant="danger">禁止</Badge> : null}
                          <Badge variant="secondary">{item.model || "auto"}</Badge>
                        </div>
                        <p className="line-clamp-3 text-sm leading-6 text-stone-700">{item.prompt_preview || "—"}</p>
                        <div className="text-xs text-stone-400">{formatTime(item.updated_at)}</div>
                        <div className="flex flex-wrap gap-2">
                          <Button
                            type="button"
                            variant="outline"
                            className="h-8 rounded-xl border-stone-200 bg-white px-2 text-xs text-stone-700"
                            disabled={isUpdating}
                            onClick={() => void patchItem(item, { is_pinned: !item.is_pinned })}
                          >
                            <Pin className="size-3.5" />
                            {item.is_pinned ? "取消置顶" : "置顶"}
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            className="h-8 rounded-xl border-stone-200 bg-white px-2 text-xs text-stone-700"
                            disabled={isUpdating}
                            onClick={() => void patchItem(item, { is_recommended: !item.is_recommended })}
                          >
                            <Star className="size-3.5" />
                            {item.is_recommended ? "取消推荐" : "推荐"}
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            className="h-8 rounded-xl border-stone-200 bg-white px-2 text-xs text-stone-700"
                            disabled={isUpdating}
                            onClick={() => void patchItem(item, { is_blocked: !item.is_blocked })}
                          >
                            <Ban className="size-3.5" />
                            {item.is_blocked ? "解除禁止" : "禁止"}
                          </Button>
                        </div>
                      </div>
                    </article>
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
