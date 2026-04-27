<h1 align="center">ChatGPT2API</h1>


<p align="center">ChatGPT2API 主要是对 ChatGPT 官网相关能力进行逆向整理与封装，提供面向 ChatGPT 图片生成、图片编辑、多图组图编辑场景的 OpenAI 兼容图片 API / 代理，并集成在线画图、号池管理、多种账号导入方式与 Docker 自托管部署能力。</p>

> [!WARNING]
> 免责声明：
>
> 本项目涉及对 ChatGPT 官网文本生成、图片生成与图片编辑等相关接口的逆向研究，仅供个人学习、技术研究与非商业性技术交流使用。
>
> - 严禁将本项目用于任何商业用途、盈利性使用、批量操作、自动化滥用或规模化调用。
> - 严禁将本项目用于破坏市场秩序、恶意竞争、套利倒卖、二次售卖相关服务，以及任何违反 OpenAI 服务条款或当地法律法规的行为。
> - 严禁将本项目用于生成、传播或协助生成违法、暴力、色情、未成年人相关内容，或用于诈骗、欺诈、骚扰等非法或不当用途。
> - 使用者应自行承担全部风险，包括但不限于账号被限制、临时封禁或永久封禁以及因违规使用等所导致的法律责任。
> - 使用本项目即视为你已充分理解并同意本免责声明全部内容；如因滥用、违规或违法使用造成任何后果，均由使用者自行承担。

> [!IMPORTANT]
> 本项目基于对 ChatGPT 官网相关能力的逆向研究实现，存在账号受限、临时封禁或永久封禁的风险。请勿使用你自己的重要账号、常用账号或高价值账号进行测试。

## 快速开始

已发布镜像支持 `linux/amd64` 与 `linux/arm64`，在 x86 服务器和 Apple Silicon / ARM Linux 设备上都会自动拉取匹配架构的版本。

```bash
git clone https://cnb.cool/gdttiti/chatgpt2api.git
# 按需编辑 config.json 的密钥、`port` 和 `refresh_account_interval_minute`
# 也可以通过环境变量覆盖同名配置项
docker compose up -d
```

默认 `docker-compose.yml` 使用 `docker.10fu.com/gdttiti/chatgpt2api:latest`，Docker 会按宿主机架构自动拉取匹配的 `amd64` 或 `arm64` 镜像。如需固定架构，可在 `.env` 中切换镜像：

```bash
CHATGPT2API_IMAGE=docker.10fu.com/gdttiti/chatgpt2api:latest-arm64
```

CNB 云原生构建会在 `main` 推送和 tag 发布时先构建并推送 CNB Artifact 多架构镜像 tag，再额外推送 `amd64` / `arm64` 单架构 tag，随后用 `skopeo copy --all` 同步完整 manifest 到：

```bash
docker.cnb.cool/gdttiti/chatgpt2api
docker.10fu.com/gdttiti/chatgpt2api
dockerhub.10fu.com/gdttiti/chatgpt2api
```

tag 规则：

```bash
# main 分支
latest
latest-amd64
latest-arm64
main
main-amd64
main-arm64
<commit>
<commit>-amd64
<commit>-arm64

# v1.2.3 这类发布 tag
v1.2.3
v1.2.3-amd64
v1.2.3-arm64
1.2.3
1.2.3-amd64
1.2.3-arm64
1.2
1.2-amd64
1.2-arm64
<commit>
<commit>-amd64
<commit>-arm64
```

外部镜像仓库同步需要在 CNB 中配置密钥变量，示例见 `.cnb/docker-envs.example.yml`：

```bash
DOCKER_10FU_USERNAME
DOCKER_10FU_PASSWORD
DOCKERHUB_10FU_USERNAME
DOCKERHUB_10FU_PASSWORD
```

如果外部镜像站密钥未配置，流水线会继续发布 CNB Artifact，并在日志中明确跳过对应镜像站；如需把外部镜像站同步设为强制要求，可设置 `EXTERNAL_REGISTRIES_REQUIRED=1`。构建日志末尾会输出本次发布摘要，按 CNB Artifact、已同步镜像站和跳过的镜像站分组列出多架构 tag 和单架构 tag。

支持通过环境变量覆盖 `config.json` 中的同名配置；环境变量非空时优先，未设置时回退到 `config.json`：

```bash
CHATGPT2API_AUTH_KEY
CHATGPT2API_PORT
CHATGPT2API_REFRESH_ACCOUNT_INTERVAL_MINUTE
CHATGPT2API_PROXY
CHATGPT2API_BASE_URL
CHATGPT2API_IMAGE_FAILURE_STRATEGY
CHATGPT2API_IMAGE_RETRY_COUNT
CHATGPT2API_IMAGE_PARALLEL_ATTEMPTS
CHATGPT2API_IMAGE_PLACEHOLDER_PATH
CHATGPT2API_IMAGE_RESPONSE_FORMAT
CHATGPT2API_IMAGE_URL_INCLUDE_B64_WHEN_REQUESTED
CHATGPT2API_IMAGE_THUMBNAIL_MAX_SIZE
CHATGPT2API_IMAGE_THUMBNAIL_QUALITY
CHATGPT2API_IMAGE_WALL_THUMBNAIL_MAX_SIZE
CHATGPT2API_OPENAI_COMPAT_IMAGE_TASK_TRACKING_ENABLED
CHATGPT2API_OPENAI_COMPAT_IMAGE_GALLERY_ENABLED
CHATGPT2API_OPENAI_COMPAT_IMAGE_WATERFALL_ENABLED
CHATGPT2API_IMAGE_RETENTION_DAYS
CHATGPT2API_TASK_LOG_RETENTION_DAYS
CHATGPT2API_DATA_CLEANUP_ENABLED
CHATGPT2API_DATA_CLEANUP_INTERVAL_MINUTES
```

启动端口额外支持通用环境变量 `PORT`。优先级是：`CHATGPT2API_PORT` > `PORT` > `config.json` 中的 `port` > 默认 `80`。

使用 `docker compose` 时，可直接在当前 shell 导出这些变量，或写入同目录 `.env` 文件，`docker-compose.yml` 已将它们透传到容器内。`config.json` 会以可写方式挂载到容器内，设置页保存的系统配置会写回该文件；如果某项环境变量为非空值，该项仍会优先覆盖 `config.json`。若同时调整容器监听端口，可再设置 `CHATGPT2API_HOST_PORT` 修改宿主机映射端口。

## 功能

### API 兼容能力

- 兼容 `POST /v1/images/generations` 图片生成接口
- 兼容 `POST /v1/images/edits` 图片编辑接口
- 兼容面向图片场景的 `POST /v1/chat/completions`
- 兼容面向图片场景的 `POST /v1/responses`
- 新增 `GET /api/catalog/models` 能力化模型目录接口
- 新增 `/api/async/jobs*` 异步任务接口，支持提交、查询、取结果与 SSE 事件流订阅
- 新增 `/api/admin/keys*` API Key 管理接口，区分管理密钥与业务调用密钥
- `GET /v1/models` 返回 `gpt-image-2`、`codex-gpt-image-2`、`auto`、`gpt-5`、`gpt-5-1`、`gpt-5-2`、`gpt-5-3`、`gpt-5-3-mini`、
  `gpt-5-mini`
- 支持通过 `n` 返回多张生成结果
- 图片生成与编辑支持 `size=1:1/4:3/3:4/3:2/16:9/21:9/9:16`；文生图额外支持合法像素尺寸，例如 `1248x1248`、`2560x1440`
- 图片生成支持 `quality=low/medium/high`，并兼容 `standard -> medium`、`hd -> high`
- 图片生成支持后台配置失败策略：`fail / retry / placeholder`
- 图片生成支持后台配置并发尝试数；单次请求可并发多个上游尝试并返回首个成功结果
- URL 返回模式会保存原图、小缩略图与瀑布墙预览图，缩略图保持原图比例，尺寸和质量可在后台或环境变量中配置
- OpenAI 兼容图片接口可配置是否创建任务跟踪、纳入画廊、纳入瀑布墙
- 当后台图片返回格式为 `url` 时，会强制返回 URL 结果；如需兼容显式请求 `response_format=b64_json` 的客户端，可开启 `image_url_include_b64_when_requested`
- 支持 Codex 中的画图接口逆向，仅 `Plus` / `Team` / `Pro` 订阅可用，模型别名为 `codex-gpt-image-2`，如有需要可自行在其他场景映射回 `gpt-image-2`，用于和官网画图区分；也就意味着同一账号会同时有官网和 Codex 两份生图额度

### 在线画图功能

- 内置在线画图工作台，支持生成、图片编辑与多图组图编辑
- 支持 `gpt-image-2`、`codex-gpt-image-2`、`auto`、`gpt-5`、`gpt-5-1`、`gpt-5-2`、`gpt-5-3`、`gpt-5-3-mini`、`gpt-5-mini` 模型选择
- 编辑模式支持参考图上传
- 前端支持多图生成交互
- 本地保存图片会话历史，支持回看、删除和清空
- 支持服务端缓存图片URL

### 号池管理功能

- 自动刷新账号邮箱、类型、额度和恢复时间
- 轮询可用账号执行图片生成与图片编辑
- 遇到 Token 失效类错误时自动剔除无效 Token
- 定时检查限流账号并自动刷新
- 支持网页端配置全局 HTTP / HTTPS / SOCKS5 / SOCKS5H 代理
- 支持搜索、筛选、批量刷新、导出、手动编辑和清理账号
- 支持四种导入方式：本地 CPA JSON 文件导入、远程 CPA 服务器导入、`sub2api` 服务器导入、`access_token` 导入
- 支持在设置页配置 `sub2api` 服务器，筛选并批量导入其中的 OpenAI OAuth 账号

### 实验性 / 规划中

- `/v1/complete` 文本补全与流式输出已实现，但仍在测试，目前会出现对话重复的问题，请谨慎测试使用
- 详细状态说明见：[功能清单](./docs/feature-status.en.md)

## Screenshots

文生图界面：

![image](assets/image.png)

编辑图：

![image](assets/image_edit.png)

Cherry Studio 中使用，支持作为绘图接口接入：

![image](assets/chery_studio.png)

号池管理：

![image](assets/account_pool.png)

New Api 接入：

![image](assets/new_api.png)

## API

管理接口继续使用 `config.json` 或 `CHATGPT2API_AUTH_KEY` 中的 `auth-key`：

```http
Authorization: Bearer <auth-key>
```

业务接口默认使用 `/api/admin/keys` 创建出的 client key：

```http
Authorization: Bearer <client-api-key>
```

<details>
<summary><code>GET /v1/models</code></summary>
<br>

返回当前暴露的图片模型列表。

```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer <auth-key>"
```

<details>
<summary>说明</summary>
<br>

| 字段   | 说明                                                                                                         |
|:-----|:-----------------------------------------------------------------------------------------------------------|
| 返回模型 | `gpt-image-2`、`codex-gpt-image-2`、`auto`、`gpt-5`、`gpt-5-1`、`gpt-5-2`、`gpt-5-3`、`gpt-5-3-mini`、`gpt-5-mini` |
| 接入场景 | 可接入 Cherry Studio、New API 等上游或客户端                                                                          |

<br>
</details>
</details>

<details>
<summary><code>GET /api/catalog/models</code></summary>
<br>

返回能力化模型目录，会在 `/v1/models` 的基础上补充每个模型可用的接口能力。

图片模型还会额外带出 `image_options`，用于表达当前支持的 `size_choices`、`quality_choices`、分辨率预设、默认尺寸和参考图能力。

</details>

<details>
<summary><code>POST /api/admin/keys</code> / <code>GET /api/admin/keys</code></summary>
<br>

用于创建、查询、启停、轮换 client API key。创建和轮换时仅返回一次明文密钥，落盘只保存 hash、前缀和元数据。

</details>

<details>
<summary><code>POST /api/async/jobs</code> / <code>GET /api/async/jobs/{job_id}/events</code></summary>
<br>

异步任务接口支持 `chat.completions`、`responses`、`images.generations`、`images.edits` 四类任务：

```bash
curl http://localhost:8000/api/async/jobs \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <client-api-key>" \
  -d '{
    "type": "chat.completions",
    "payload": {
      "model": "auto",
      "messages": [
        {"role": "user", "content": "hello"}
      ]
    }
  }'
```

图片类异步任务的 `payload` 也支持 `size` 和 `quality`，例如 `{"size":"1440x1072","quality":"high"}`。任务运行中可订阅 `GET /api/async/jobs/{job_id}/events`。服务会持续发送 `event: ping` 保持 SSE 连接，任务完成后推送 `event: result` 或 `event: error`。

</details>

<details>
<summary><code>POST /v1/images/generations</code></summary>
<br>

OpenAI 兼容图片生成接口，用于文生图。

```bash
curl http://localhost:8000/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "一只漂浮在太空里的猫",
    "n": 1,
    "size": "1440x1072",
    "quality": "high",
    "response_format": "b64_json"
  }'
```

<details>
<summary>字段说明</summary>
<br>

| 字段                | 说明                                                 |
|:------------------|:---------------------------------------------------|
| `model`           | 图片模型，当前可用值以 `/v1/models` 返回结果为准，推荐使用 `gpt-image-2` |
| `prompt`          | 图片生成提示词                                            |
| `n`               | 生成数量，当前后端限制为 `1-4`                                 |
| `size`            | 可选尺寸/比例，支持 `1:1`、`4:3`、`3:4`、`3:2`、`16:9`、`21:9`、`9:16`，也支持合法像素尺寸如 `1248x1248` |
| `quality`         | 可选生成质量，支持 `low`、`medium`、`high`，兼容 `standard` 和 `hd` |
| `response_format` | 当前请求模型中包含该字段，默认值为 `b64_json`                       |

<br>
</details>
</details>

<details>
<summary><code>POST /v1/images/edits</code></summary>
<br>

OpenAI 兼容图片编辑接口，用于上传图片并生成编辑结果。

```bash
curl http://localhost:8000/v1/images/edits \
  -H "Authorization: Bearer <auth-key>" \
  -F "model=gpt-image-2" \
  -F "prompt=把这张图改成赛博朋克夜景风格" \
  -F "n=1" \
  -F "size=9:16" \
  -F "image=@./input.png"
```

<details>
<summary>字段说明</summary>
<br>

| 字段       | 说明                                  |
|:---------|:------------------------------------|
| `model`  | 图片模型， `gpt-image-2`                 |
| `prompt` | 图片编辑提示词                             |
| `n`      | 生成数量，当前后端限制为 `1-4`                  |
| `size`   | 可选尺寸/比例，支持 `1:1`、`4:3`、`3:4`、`3:2`、`16:9`、`21:9`、`9:16` |
| `image`  | 需要编辑的图片文件，使用 multipart/form-data 上传 |

<br>
</details>
</details>

<details>
<summary><code>POST /v1/chat/completions</code></summary>
<br>

面向图片场景的 Chat Completions 兼容接口，不是完整通用聊天代理。

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{
    "model": "gpt-image-2",
    "messages": [
      {
        "role": "user",
        "content": "生成一张雨夜东京街头的赛博朋克猫"
      }
    ],
    "n": 1
  }'
```

<details>
<summary>字段说明</summary>
<br>

| 字段         | 说明                |
|:-----------|:------------------|
| `model`    | 图片模型，默认按图片生成场景处理  |
| `messages` | 消息数组，需要是图片相关请求内容  |
| `n`        | 生成数量，按当前实现解析为图片数量 |
| `stream`   | 已实现，但仍在测试         |

<br>
</details>
</details>

<details>
<summary><code>POST /v1/responses</code></summary>
<br>

面向图片生成工具调用的 Responses API 兼容接口，不是完整通用 Responses API 代理。

```bash
curl http://localhost:8000/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{
    "model": "gpt-5",
    "input": "生成一张未来感城市天际线图片",
    "tools": [
      {
        "type": "image_generation"
      }
    ]
  }'
```

<details>
<summary>字段说明</summary>
<br>

| 字段       | 说明                            |
|:---------|:------------------------------|
| `model`  | 响应中会回显该模型字段，但图片生成当前仍走图片生成兼容逻辑 |
| `input`  | 输入内容，需要能解析出图片生成提示词            |
| `tools`  | 必须包含 `image_generation` 工具请求  |
| `stream` | 已实现，但仍在测试                     |

<br>
</details>
</details>

## 社区支持

学 AI , 上 L 站：[LinuxDO](https://linux.do)

## Contributors

感谢所有为本项目做出贡献的开发者：

<a href="https://github.com/basketikun/chatgpt2api/graphs/contributors">
  <img alt="Contributors" src="https://contrib.rocks/image?repo=basketikun/chatgpt2api" />
</a>

## Star History

[![Star History Chart](https://api.star-history.com/chart?repos=basketikun/chatgpt2api&type=date&legend=top-left)](https://www.star-history.com/?repos=basketikun%2Fchatgpt2api&type=date&legend=top-left)
