"use client";

import { ExternalLink, FileJson } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const authExample = `# 管理接口
Authorization: Bearer <auth-key>

# 业务接口
Authorization: Bearer <client-api-key>`;

const modelsExample = `curl http://localhost:8000/v1/models \\
  -H "Authorization: Bearer <client-api-key>"`;

const catalogExample = `curl http://localhost:8000/api/catalog/models \\
  -H "Authorization: Bearer <client-api-key>"`;

const adminKeysExample = `curl http://localhost:8000/api/admin/keys \\
  -H "Authorization: Bearer <auth-key>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "ci-runner",
    "allowed_models": ["gpt-image-2", "auto"],
    "scopes": ["inference"]
  }'`;

const asyncExample = `curl http://localhost:8000/api/async/jobs \\
  -H "Authorization: Bearer <client-api-key>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "type": "images.generations",
    "payload": {
      "model": "gpt-image-2",
      "prompt": "一张雨夜东京街头的赛博朋克猫",
      "size": "16:9"
    }
  }'`;

const asyncSseExample = `curl -N http://localhost:8000/api/async/jobs/<job_id>/events \\
  -H "Authorization: Bearer <client-api-key>"`;

const asyncResultExample = `curl http://localhost:8000/api/async/jobs/<job_id>/result \\
  -H "Authorization: Bearer <client-api-key>"`;

const imageExample = `curl http://localhost:8000/v1/images/generations \\
  -H "Authorization: Bearer <client-api-key>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gpt-image-2",
    "prompt": "一张极简海报风格的山野露营插画",
    "size": "1440x1072",
    "quality": "high",
    "n": 1,
    "response_format": "url"
  }'`;

const editExample = `curl http://localhost:8000/v1/images/edits \\
  -H "Authorization: Bearer <client-api-key>" \\
  -F "model=gpt-image-2" \\
  -F "prompt=把这张图改成电影感夜景" \\
  -F "size=9:16" \\
  -F "image=@./input.png"`;

const envExample = `CHATGPT2API_PORT > PORT > config.json.port > 80
CHATGPT2API_IMAGE_FAILURE_STRATEGY
CHATGPT2API_IMAGE_RETRY_COUNT
CHATGPT2API_IMAGE_PARALLEL_ATTEMPTS
CHATGPT2API_IMAGE_PLACEHOLDER_PATH
CHATGPT2API_IMAGE_RESPONSE_FORMAT
CHATGPT2API_IMAGE_THUMBNAIL_MAX_SIZE
CHATGPT2API_IMAGE_THUMBNAIL_QUALITY
CHATGPT2API_IMAGE_WALL_THUMBNAIL_MAX_SIZE
CHATGPT2API_IMAGE_RETENTION_DAYS
CHATGPT2API_TASK_LOG_RETENTION_DAYS
CHATGPT2API_DATA_CLEANUP_ENABLED
CHATGPT2API_DATA_CLEANUP_INTERVAL_MINUTES`;

const imageGetExample = `curl http://localhost:8000/api/view/data/2026-04-25/<task-id>-1.png`;

const endpointGroups = [
  {
    name: "OpenAI 兼容接口",
    items: [
      ["GET", "/v1/models", "返回 OpenAI 风格模型列表"],
      ["POST", "/v1/chat/completions", "同步或流式 Chat Completions"],
      ["POST", "/v1/responses", "Responses 兼容接口"],
      ["POST", "/v1/images/generations", "文生图，支持 size / quality / response_format"],
      ["POST", "/v1/images/edits", "图生图，支持单图和多参考图"],
    ],
  },
  {
    name: "异步任务",
    items: [
      ["POST", "/api/async/jobs", "提交图片、chat.completions、responses 异步任务"],
      ["GET", "/api/async/jobs", "分页查询任务列表"],
      ["GET", "/api/async/jobs/{job_id}", "查询任务状态"],
      ["GET", "/api/async/jobs/{job_id}/events", "SSE 订阅任务进度与结果"],
      ["GET", "/api/async/jobs/{job_id}/result", "读取任务结果"],
      ["GET", "/api/async/jobs/{job_id}/log", "读取任务日志"],
    ],
  },
  {
    name: "管理与配置",
    items: [
      ["GET/POST", "/api/admin/keys", "管理 client API key"],
      ["GET/POST", "/api/accounts", "账号列表、导入与刷新"],
      ["GET/POST", "/api/settings/config", "读取和保存系统配置"],
      ["GET", "/api/catalog/models", "读取模型能力目录"],
      ["GET", "/api/view/data/{path}", "读取服务端保存的图片文件"],
    ],
  },
] as const;

function CodeBlock({ value }: { value: string }) {
  return (
    <pre className="overflow-x-auto rounded-2xl bg-stone-950 px-4 py-4 text-xs leading-6 text-stone-100">
      <code>{value}</code>
    </pre>
  );
}

export default function DocsPage() {
  return (
    <section className="mx-auto flex w-full max-w-[1240px] flex-col gap-6 pb-8">
      <div className="space-y-2">
        <div className="text-xs font-semibold tracking-[0.18em] text-stone-500 uppercase">API Docs</div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">API 使用说明</h1>
          <Badge variant="secondary">Swagger 已内嵌</Badge>
          <Badge variant="info">OpenAI 兼容图片接口</Badge>
          <Badge variant="success">quality 已支持</Badge>
        </div>
        <p className="max-w-[900px] text-sm leading-7 text-stone-500">
          以 Swagger / OpenAPI 作为完整接口事实源，页面下方保留最常用的鉴权、图片、异步任务和文件访问示例。网页画图页现已固定走异步 SSE；文生图支持
          `size`、分辨率预设和 `quality=low/medium/high`。
        </p>
      </div>

      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="space-y-4 p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <h2 className="text-lg font-semibold tracking-tight">Swagger / OpenAPI</h2>
              <p className="max-w-[820px] text-sm leading-6 text-stone-500">
                完整接口、参数结构和响应模型以 FastAPI 自动生成的 Swagger 为准。需要复制 schema 或生成 SDK 时使用 OpenAPI JSON。
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button asChild variant="outline" className="rounded-xl border-stone-200 bg-white">
                <a href="/swagger" target="_blank" rel="noreferrer">
                  <ExternalLink className="size-4" />
                  打开 Swagger
                </a>
              </Button>
              <Button asChild variant="outline" className="rounded-xl border-stone-200 bg-white">
                <a href="/openapi.json" target="_blank" rel="noreferrer">
                  <FileJson className="size-4" />
                  OpenAPI JSON
                </a>
              </Button>
            </div>
          </div>
          <div className="overflow-hidden rounded-2xl border border-stone-200 bg-white">
            <iframe
              title="Swagger API Docs"
              src="/swagger"
              className="h-[720px] w-full bg-white"
            />
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="space-y-5 p-6">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold tracking-tight">接口索引</h2>
            <p className="text-sm text-stone-500">常用接口按调用场景整理；详细请求体和响应体查看上方 Swagger。</p>
          </div>
          <div className="grid gap-4 xl:grid-cols-3">
            {endpointGroups.map((group) => (
              <div key={group.name} className="overflow-hidden rounded-2xl border border-stone-200 bg-white">
                <div className="border-b border-stone-200 bg-stone-50 px-4 py-3 text-sm font-semibold text-stone-900">
                  {group.name}
                </div>
                <div className="divide-y divide-stone-100">
                  {group.items.map(([method, path, description]) => (
                    <div key={`${method}-${path}`} className="space-y-1 px-4 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="secondary" className="rounded-full px-2 py-0.5 text-[11px]">
                          {method}
                        </Badge>
                        <code className="break-all text-xs font-semibold text-stone-900">{path}</code>
                      </div>
                      <p className="text-xs leading-5 text-stone-500">{description}</p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
          <CardContent className="space-y-4 p-6">
            <div className="space-y-1">
              <h2 className="text-lg font-semibold tracking-tight">鉴权方式</h2>
              <p className="text-sm text-stone-500">后台管理接口继续使用管理员登录密钥，业务调用接口建议使用 client key。</p>
            </div>
            <CodeBlock value={authExample} />
          </CardContent>
        </Card>

        <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
          <CardContent className="space-y-4 p-6">
            <div className="space-y-1">
              <h2 className="text-lg font-semibold tracking-tight">图片参数说明</h2>
              <p className="text-sm text-stone-500">
                当前已支持 `size=1:1/4:3/3:4/3:2/16:9/21:9/9:16`，网页也可填写自定义尺寸文本，例如 `1248x1248` 或 `21:9`。文生图会校验像素尺寸并透传
                `quality=low/medium/high`。图片返回格式支持
                `b64_json` 和 `url`；未配置外链地址时，`url` 会返回相对路径 `/api/view/data/...`。缩略图与瀑布墙预览图都会保持原图比例，尺寸和质量可在设置页或环境变量中配置。
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {["1:1", "4:3", "3:4", "3:2", "16:9", "21:9", "9:16"].map((item) => (
                <Badge key={item} variant="secondary" className="rounded-full px-3 py-1">
                  {item}
                </Badge>
              ))}
            </div>
            <CodeBlock value={envExample} />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
          <CardContent className="space-y-4 p-6">
            <div className="space-y-1">
              <h2 className="text-lg font-semibold tracking-tight">模型列表</h2>
              <p className="text-sm text-stone-500">`/v1/models` 返回 OpenAI 风格模型列表，`/api/catalog/models` 会补能力说明；网页画图页会基于这里的结果切换模型，并受 API key 模型限制约束。</p>
            </div>
            <CodeBlock value={modelsExample} />
            <CodeBlock value={catalogExample} />
          </CardContent>
        </Card>

        <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
          <CardContent className="space-y-4 p-6">
            <div className="space-y-1">
              <h2 className="text-lg font-semibold tracking-tight">异步任务</h2>
              <p className="text-sm text-stone-500">
                `/api/async/jobs` 支持图片生成、图片编辑、chat.completions、responses。建议直接使用 SSE 订阅任务事件；SSE 通道会持续发送
                `ping` 保活，图片页也是基于这条链路。
              </p>
            </div>
            <CodeBlock value={asyncExample} />
            <CodeBlock value={asyncSseExample} />
            <CodeBlock value={asyncResultExample} />
          </CardContent>
        </Card>

        <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
          <CardContent className="space-y-4 p-6">
            <div className="space-y-1">
              <h2 className="text-lg font-semibold tracking-tight">API Key 管理接口</h2>
              <p className="text-sm text-stone-500">
                后台可创建、停用、轮换和删除 client key。可设置请求次数上限、图片次数上限和允许模型；明文 key 只在创建和轮换时返回一次。
              </p>
            </div>
            <CodeBlock value={adminKeysExample} />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
          <CardContent className="space-y-4 p-6">
            <div className="space-y-1">
              <h2 className="text-lg font-semibold tracking-tight">文生图</h2>
              <p className="text-sm text-stone-500">兼容 `POST /v1/images/generations`，建议显式传 `size` 与 `response_format`。当服务端配置为 `url` 返回时，结果可直接展示或再次由服务端转发。</p>
            </div>
            <CodeBlock value={imageExample} />
          </CardContent>
        </Card>

        <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
          <CardContent className="space-y-4 p-6">
            <div className="space-y-1">
              <h2 className="text-lg font-semibold tracking-tight">图生图</h2>
              <p className="text-sm text-stone-500">
                兼容 `POST /v1/images/edits`，支持单图和多参考图。当前比例选择与文生图一致。
              </p>
            </div>
            <CodeBlock value={editExample} />
          </CardContent>
        </Card>
      </div>

      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="space-y-4 p-6">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold tracking-tight">图片文件与清理</h2>
            <p className="text-sm text-stone-500">
              图片会保存到 `data/YYYY-MM-DD/task-id-index.ext`，缩略图会保存为 `task-id-index-thumb.ext`，瀑布墙预览会保存为 `task-id-index-wall.ext`。可通过设置页配置缩略图尺寸、质量、瀑布墙预览尺寸、图片保留天数、任务日志保留天数、系统日志体积和自动清理间隔。
            </p>
          </div>
          <CodeBlock value={imageGetExample} />
          <CodeBlock value={envExample} />
        </CardContent>
      </Card>
    </section>
  );
}
