"use client";

import { ArrowUp, ImagePlus, LoaderCircle, Settings2, X } from "lucide-react";
import { useMemo, useState, type ClipboardEvent, type RefObject } from "react";

import { ImageLightbox } from "@/components/image-lightbox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { IMAGE_SIZE_OPTIONS } from "@/lib/api";
import type { ImageConversationMode, ImageRequestMode } from "@/store/image-conversations";
import { cn } from "@/lib/utils";

const CUSTOM_SIZE_VALUE = "__custom__";

type ImageComposerProps = {
  mode: ImageConversationMode;
  prompt: string;
  imageModel: string;
  imageModels: string[];
  modelLocked?: boolean;
  requestMode: ImageRequestMode;
  imageCount: string;
  imageSize: string;
  imageSizePreset: string;
  customImageSize: string;
  availableQuota: string;
  requestQuota?: string | null;
  isTestMode?: boolean;
  activeTaskCount: number;
  referenceImages: Array<{ name: string; dataUrl: string }>;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  fileInputRef: RefObject<HTMLInputElement | null>;
  onModeChange: (value: ImageConversationMode) => void;
  onPromptChange: (value: string) => void;
  onImageModelChange: (value: string) => void;
  onRequestModeChange: (value: ImageRequestMode) => void;
  onImageCountChange: (value: string) => void;
  onImageSizePresetChange: (value: string) => void;
  onCustomImageSizeChange: (value: string) => void;
  onSubmit: () => void | Promise<void>;
  onPickReferenceImage: () => void;
  onReferenceImageChange: (files: File[]) => void | Promise<void>;
  onRemoveReferenceImage: (index: number) => void;
};

export function ImageComposer({
  mode,
  prompt,
  imageModel,
  imageModels,
  modelLocked = false,
  requestMode,
  imageCount,
  imageSize,
  imageSizePreset,
  customImageSize,
  availableQuota,
  requestQuota,
  isTestMode = false,
  activeTaskCount,
  referenceImages,
  textareaRef,
  fileInputRef,
  onModeChange,
  onPromptChange,
  onImageModelChange,
  onRequestModeChange,
  onImageCountChange,
  onImageSizePresetChange,
  onCustomImageSizeChange,
  onSubmit,
  onPickReferenceImage,
  onReferenceImageChange,
  onRemoveReferenceImage,
}: ImageComposerProps) {
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [draftImageModel, setDraftImageModel] = useState(imageModel);
  const [draftRequestMode, setDraftRequestMode] = useState<ImageRequestMode>(requestMode);
  const [draftImageCount, setDraftImageCount] = useState(imageCount);
  const [draftImageSizePreset, setDraftImageSizePreset] = useState(imageSizePreset);
  const [draftCustomImageSize, setDraftCustomImageSize] = useState(customImageSize);
  const lightboxImages = useMemo(
    () => referenceImages.map((image, index) => ({ id: `${image.name}-${index}`, src: image.dataUrl })),
    [referenceImages],
  );

  const handleTextareaPaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const imageFiles = Array.from(event.clipboardData.files).filter((file) => file.type.startsWith("image/"));
    if (imageFiles.length === 0) {
      return;
    }

    event.preventDefault();
    void onReferenceImageChange(imageFiles);
  };

  const openSettings = () => {
    setDraftImageModel(imageModel);
    setDraftRequestMode(requestMode);
    setDraftImageCount(imageCount);
    setDraftImageSizePreset(imageSizePreset);
    setDraftCustomImageSize(customImageSize);
    setSettingsOpen(true);
  };

  const applySettings = () => {
    onImageModelChange(draftImageModel);
    onRequestModeChange(draftRequestMode);
    onImageCountChange(draftImageCount);
    onImageSizePresetChange(draftImageSizePreset);
    onCustomImageSizeChange(draftCustomImageSize);
    setSettingsOpen(false);
  };

  return (
    <div className="shrink-0 flex justify-center">
      <div style={{ width: "min(980px, 100%)" }}>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(event) => {
            void onReferenceImageChange(Array.from(event.target.files || []));
          }}
        />

        {referenceImages.length > 0 ? (
          <div className="mb-3 flex flex-wrap gap-2 px-1">
            {referenceImages.map((image, index) => (
              <div key={`${image.name}-${index}`} className="relative size-16">
                <button
                  type="button"
                  onClick={() => {
                    setLightboxIndex(index);
                    setLightboxOpen(true);
                  }}
                  className="group size-16 overflow-hidden rounded-2xl border border-stone-200 bg-stone-50 transition hover:border-stone-300"
                  aria-label={`预览参考图 ${image.name || index + 1}`}
                >
                  <img
                    src={image.dataUrl}
                    alt={image.name || `参考图 ${index + 1}`}
                    className="h-full w-full object-cover"
                  />
                </button>
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onRemoveReferenceImage(index);
                  }}
                  className="absolute -right-1 -top-1 inline-flex size-5 items-center justify-center rounded-full border border-stone-200 bg-white text-stone-500 transition hover:border-stone-300 hover:text-stone-800"
                  aria-label={`移除参考图 ${image.name || index + 1}`}
                >
                  <X className="size-3" />
                </button>
              </div>
            ))}
          </div>
        ) : null}

        <div className="overflow-hidden rounded-[32px] border border-stone-200 bg-white">
          <div
            className="relative cursor-text"
            onClick={() => {
              textareaRef.current?.focus();
            }}
          >
            <ImageLightbox
              images={lightboxImages}
              currentIndex={lightboxIndex}
              open={lightboxOpen}
              onOpenChange={setLightboxOpen}
              onIndexChange={setLightboxIndex}
            />
            <Textarea
              ref={textareaRef}
              value={prompt}
              onChange={(event) => onPromptChange(event.target.value)}
              onPaste={handleTextareaPaste}
              placeholder={
                mode === "edit" ? "描述你希望如何修改这张参考图，可直接粘贴图片" : "输入你想要生成的画面，也可直接粘贴图片"
              }
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void onSubmit();
                }
              }}
              className="min-h-[148px] resize-none rounded-[32px] border-0 bg-transparent px-6 pt-6 pb-20 text-[15px] leading-7 text-stone-900 shadow-none placeholder:text-stone-400 focus-visible:ring-0"
            />

            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-white via-white/95 to-transparent px-4 pb-4 pt-6 sm:px-6">
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <ModeButton active={mode === "generate"} onClick={() => onModeChange("generate")}>
                    文生图
                  </ModeButton>
                  <ModeButton active={mode === "edit"} onClick={() => onModeChange("edit")}>
                    图生图
                  </ModeButton>
                  {mode === "edit" ? (
                    <Button
                      type="button"
                      variant="outline"
                      className="h-10 rounded-full border-stone-200 bg-white px-4 text-sm font-medium text-stone-700 shadow-none"
                      onClick={onPickReferenceImage}
                    >
                      <ImagePlus className="size-4" />
                      {referenceImages.length > 0 ? "继续添加参考图" : "上传参考图"}
                    </Button>
                  ) : null}
                  <div className="rounded-full bg-stone-100 px-3 py-2 text-xs font-medium text-stone-600">
                    剩余图片额度 {availableQuota}
                  </div>
                  {requestQuota ? (
                    <div className="rounded-full bg-stone-100 px-3 py-2 text-xs font-medium text-stone-600">
                      剩余请求次数 {requestQuota}
                    </div>
                  ) : null}
                  {isTestMode ? (
                    <div className="rounded-full bg-sky-50 px-3 py-2 text-xs font-medium text-sky-700">测试模式</div>
                  ) : null}
                  {activeTaskCount > 0 ? (
                    <div className="flex items-center gap-1.5 rounded-full bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">
                      <LoaderCircle className="size-3 animate-spin" />
                      {activeTaskCount} 个任务处理中或排队中
                    </div>
                  ) : null}
                </div>

                <div className="flex items-end justify-between gap-3">
                  <div className="min-w-0 px-1 text-[11px] text-stone-400">
                    当前参数: model={imageModel} / size={imageSize || "1:1"} / mode={requestMode}
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      className="h-11 rounded-full border-stone-200 bg-white px-4 text-sm font-medium text-stone-700"
                      onClick={openSettings}
                    >
                      <Settings2 className="size-4" />
                      设置
                    </Button>
                    <button
                      type="button"
                      onClick={() => void onSubmit()}
                      disabled={!prompt.trim() || (mode === "edit" && referenceImages.length === 0)}
                      className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-stone-950 text-white transition hover:bg-stone-800 disabled:cursor-not-allowed disabled:bg-stone-300"
                      aria-label={mode === "edit" ? "编辑图片" : "生成图片"}
                    >
                      <ArrowUp className="size-4" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
          <DialogContent className="max-w-[720px] rounded-[28px]">
            <DialogHeader>
              <DialogTitle>会话参数设置</DialogTitle>
              <DialogDescription>修改当前会话的模型、调用方式和图片参数，保存后立即用于后续提交。</DialogDescription>
            </DialogHeader>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <div className="text-sm font-medium text-stone-700">模型</div>
                <Select value={draftImageModel} onValueChange={setDraftImageModel} disabled={modelLocked}>
                  <SelectTrigger className="h-11 rounded-xl border-stone-200 bg-white">
                    <SelectValue placeholder="选择模型" />
                  </SelectTrigger>
                  <SelectContent>
                    {imageModels.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {modelLocked ? (
                  <p className="text-xs leading-5 text-stone-500">当前 key 已限制模型，前端仅展示可用模型。</p>
                ) : null}
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium text-stone-700">调用方式</div>
                <Select value={draftRequestMode} onValueChange={(value) => setDraftRequestMode(value as ImageRequestMode)}>
                  <SelectTrigger className="h-11 rounded-xl border-stone-200 bg-white">
                    <SelectValue placeholder="选择方式" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="direct">直连接口</SelectItem>
                    <SelectItem value="async_http">异步 HTTP</SelectItem>
                    <SelectItem value="async_sse">异步 SSE</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium text-stone-700">张数</div>
                <Input
                  type="number"
                  min="1"
                  max="10"
                  step="1"
                  value={draftImageCount}
                  onChange={(event) => setDraftImageCount(event.target.value)}
                  className="h-11 rounded-xl border-stone-200 bg-white"
                />
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium text-stone-700">分辨率 / 比例</div>
                <Select value={draftImageSizePreset} onValueChange={setDraftImageSizePreset}>
                  <SelectTrigger className="h-11 rounded-xl border-stone-200 bg-white">
                    <SelectValue placeholder="选择比例" />
                  </SelectTrigger>
                  <SelectContent>
                    {IMAGE_SIZE_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                    <SelectItem value={CUSTOM_SIZE_VALUE}>自定义</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {draftImageSizePreset === CUSTOM_SIZE_VALUE ? (
                <div className="space-y-2 md:col-span-2">
                  <div className="text-sm font-medium text-stone-700">自定义尺寸</div>
                  <Input
                    value={draftCustomImageSize}
                    onChange={(event) => setDraftCustomImageSize(event.target.value)}
                    placeholder="例如 1024x1024 或 21:9"
                    className="h-11 rounded-xl border-stone-200 bg-white"
                  />
                  <p className="text-xs leading-5 text-stone-500">会原样透传到后端，请按当前模型支持的格式填写。</p>
                </div>
              ) : null}

              <div className="space-y-2 md:col-span-2">
                <div className="text-sm font-medium text-stone-700">质量</div>
                <div className="flex items-center gap-2 rounded-xl border border-dashed border-stone-200 bg-stone-50 px-4 py-3">
                  <Badge variant="outline" className="rounded-full border-stone-200 bg-white text-stone-500">
                    暂未支持
                  </Badge>
                  <span className="text-sm text-stone-500">后端当前没有 `quality` 契约，界面仅保留占位说明。</span>
                </div>
              </div>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" className="rounded-xl border-stone-200" onClick={() => setSettingsOpen(false)}>
                关闭
              </Button>
              <Button type="button" className="rounded-xl bg-stone-950 text-white hover:bg-stone-800" onClick={applySettings}>
                保存设置
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}

function ModeButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full px-4 py-2 text-sm font-medium transition",
        active ? "bg-stone-950 text-white" : "bg-stone-100 text-stone-600 hover:bg-stone-200",
      )}
    >
      {children}
    </button>
  );
}
