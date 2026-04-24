"use client";

import { Badge } from "@/components/ui/badge";
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

const imageExample = `curl http://localhost:8000/v1/images/generations \\
  -H "Authorization: Bearer <client-api-key>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gpt-image-2",
    "prompt": "一张极简海报风格的山野露营插画",
    "size": "4:3",
    "n": 1,
    "response_format": "b64_json"
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
CHATGPT2API_IMAGE_PLACEHOLDER_PATH`;

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
          <Badge variant="info">OpenAI 兼容图片接口</Badge>
          <Badge variant="warning">quality 当前未支持</Badge>
        </div>
        <p className="max-w-[900px] text-sm leading-7 text-stone-500">
          页面内汇总了下游接入时最常用的鉴权方式、模型接口、异步任务接口和图片参数约束。当前前端支持比例
          `size` 选择，质量 `quality` 还没有进入后端契约。
        </p>
      </div>

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
                当前已支持 `size=1:1/16:9/9:16/4:3/3:4`。失败策略、重试次数、并发尝试和占位图由后台配置控制。
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {["1:1", "16:9", "9:16", "4:3", "3:4"].map((item) => (
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
              <p className="text-sm text-stone-500">`/v1/models` 返回 OpenAI 风格模型列表，`/api/catalog/models` 会补能力说明。</p>
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
                `/api/async/jobs` 支持图片生成、图片编辑、chat.completions、responses。SSE 订阅会持续发送 `ping` 保活。
              </p>
            </div>
            <CodeBlock value={asyncExample} />
          </CardContent>
        </Card>

        <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
          <CardContent className="space-y-4 p-6">
            <div className="space-y-1">
              <h2 className="text-lg font-semibold tracking-tight">API Key 管理接口</h2>
              <p className="text-sm text-stone-500">
                后台可创建、停用、轮换和删除 client key。明文 key 只在创建和轮换时返回一次。
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
              <p className="text-sm text-stone-500">兼容 `POST /v1/images/generations`，建议显式传 `size` 与 `response_format`。</p>
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
    </section>
  );
}
