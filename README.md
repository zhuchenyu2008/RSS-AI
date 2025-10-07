# RSS‑AI

一个前后端分离的 RSS 助手：定时抓取多个 RSS 源，使用用户自定义的 AI（OpenAI 通用格式）对最新文章进行总结并排版，去重入库，推送到 Telegram 群组，同时提供标准 API 与前端 Web 管理界面。默认监听端口 `3601`。

– 后端：Python + FastAPI（含 OpenAPI/Swagger、详细日志、可热更新配置、后台定时任务）
– 前端：黑白配色、简约高级的 Web 页面（查看摘要与在线修改配置）

注意：本仓库为可直接运行的完整实现；首次运行会自动生成 `backend/config.yaml`。

## 图片


<details>
<summary>WEB</summary>
    
  ![屏幕截图_6-10-2025_11614_rss zhuchenyu cn](https://github.com/user-attachments/assets/8632d112-dcc7-4fe6-a4a2-0a68f67b6e9f)
    ![屏幕截图_6-10-2025_11638_rss zhuchenyu cn](https://github.com/user-attachments/assets/b9de54ea-8a70-4314-9d9e-42a8fd12e3bf)
</details>


<details>
<summary>telegram</summary>
    <img width="1480" height="897" alt="Desktop Screenshot 2025 10 06 - 11 07 55 93" src="https://github.com/user-attachments/assets/e78dc129-af0b-40bd-bdca-dfcd8aa02132" />


</details>



## 功能概览

- 定时抓取：从配置文件读取多个 RSS 源，按间隔抓取最新文章。
- AI 总结：支持先抓取原文网页并抽取正文，再送入用户配置的 OpenAI 兼容接口，输出 JSON，字段包含：
  - `title` 标题
  - `link` 原始网页 URL
  - `pubDate` 发布时间
  - `author` 作者
  - `summary_text` AI 中文总结
- 关键词过滤与标注：支持在配置中维护关键词列表，仅保留命中关键词的文章；命中的关键词会同步展示在 Web 列表、弹窗与 Telegram 推送，方便快速定位关注点（英文匹配区分大小写）。
- 去重与存储：使用 SQLite 本地存储，基于 `feed_url + item_uid` 唯一约束去重；可配置最大存储条数，自动裁剪旧数据。
- 单源抓取上限：可为每个 RSS 源设置“单次抓取最多处理 N 条”，按时间倒序优先（越新越先处理）。
- Telegram 推送：将 AI 总结以精简排版推送到指定群组或频道。
- 抓取汇总推送（可选）：可将每次抓取的汇总信息（条目总数、入库成功/重复/失败、AI 调用成功/失败次数、Token 消耗等）推送到 Telegram。
- 标准 API：提供 RESTful 接口与 `/docs` Swagger UI。
- 前端管理：查看摘要列表、手动抓取、在线修改配置（无需重启服务）。
 - 可自定义提示词：支持自定义 System Prompt 与 User Prompt 模板（可用 {title}、{link}、{pub_date}、{author}、{content} 占位符）。

## 目录结构

- `backend/` 后端源码与依赖
  - `app/` FastAPI 应用主体
    - `main.py` 启动入口（含 API、依赖注入与路由）
    - `scheduler.py` 抓取调度器，包含定时任务与热更新逻辑
    - `rss_service.py` RSS 抓取、去重与正文抽取流程
    - `ai_client.py`/`telegram_client.py` AI 与 Telegram 适配器
    - `storage.py`/`models.py` SQLite 数据访问层
    - `report_service.py` 周期汇总报告的生成与推送
  - `config.yaml` 运行时配置（首次启动自动生成，可在前端修改并回写）
  - `data/` SQLite 数据文件，默认持久化于本地
  - `logs/` 运行日志目录
  - `requirements.txt` 后端依赖声明
  - `run.sh` & `Dockerfile` 快速启动/容器化脚本
- `frontend/` 前端静态页面（原生 HTML/CSS/JS）
  - `index.html` 与 `styles.css` UI 布局与样式
  - `app.js` 调用后端 API、处理设置保存与手动抓取
  - `server.py`/`run.sh` 简易静态文件服务器（支持 `/api` 反代）

## 快速开始

1) 准备环境

- Python 3.10+
- 可选：创建虚拟环境 `python -m venv .venv && source .venv/bin/activate`

```
git clone https://github.com/zhuchenyu2008/RSS-AI
cd RSS-AI
```

2) 安装依赖并启动后端（端口 3601）

```
cd backend
pip install -r requirements.txt
./run.sh
```

后端启动后监听 `http://127.0.0.1:3601`，Swagger UI 在 `http://127.0.0.1:3601/docs`。

3) 启动前端服务（端口 3602，同源访问 + 反向代理 /api）

```
cd frontend
PORT=3602 BACKEND_BASE_URL=http://127.0.0.1:3601 ./run.sh
```

打开浏览器访问 `http://127.0.0.1:3602`。该前端服务会将 `/api/*` 请求反向代理到后端 3601，实现同源访问，无需 CORS。

## 使用 Docker 运行（推荐）

### 使用 Docker Hub 预构建镜像

已在 Docker Hub 发布官方镜像，可直接拉取并运行：

```bash
docker pull zhuchenyu2008/rss-ai-backend
docker pull zhuchenyu2008/rss-ai-frontend
```

若仅使用后端，可通过以下命令启动（默认监听 3601 端口）：

```bash
docker run -d \
  --name rss-ai-backend \
  -p 3601:3601 \
  -v "$(pwd)/backend/config.yaml:/app/config.yaml" \
  -v "$(pwd)/backend/data:/app/data" \
  -v "$(pwd)/backend/logs:/app/logs" \
  zhuchenyu2008/rss-ai-backend
```

前端镜像为纯静态资源服务，需要指定后端地址并映射 3602 端口：

```bash
docker run -d \
  --name rss-ai-frontend \
  -p 3602:3602 \
  -e BACKEND_BASE_URL="http://127.0.0.1:3601" \
  zhuchenyu2008/rss-ai-frontend
```

两者配合使用时，请保证前端容器能够访问后端地址（可在同一主机使用默认端口，或结合反向代理/自定义网络）。

确保已安装 Docker 与 Docker Compose：

```
docker compose build
docker compose up -d
```

启动完成后：

- 后端 API：http://127.0.0.1:3601 （Swagger: /docs）
- 前端 Web：http://127.0.0.1:3602 （同源反代到后端）

数据与配置持久化：

- `backend/config.yaml` 会被挂载到容器 `/app/config.yaml`，可本地编辑后热更新（保存配置也会写回本地文件）。
- `backend/logs/` 与 `backend/data/` 挂载为持久化目录（日志与 SQLite 数据库）。

常用命令：

```
# 查看日志
docker compose logs -f backend
docker compose logs -f frontend

# 重建镜像
docker compose build --no-cache

# 停止并移除容器
docker compose down
```

## 配置说明（backend/config.yaml）

首次运行若不存在会自动从内置模板生成。核心结构示例：

```yaml
server:
  host: 0.0.0.0
  port: 3601

fetch:
  interval_minutes: 10        # 抓取间隔（分钟），保存配置后自动热更新
  max_items: 500              # SQLite 存储上限（超出后裁剪最旧记录）
  feeds:                      # RSS 列表
    - https://example.com/rss
  filter_keywords: []         # 命中才会入库/推送；留空表示不过滤，填写时请删除 [] 并逐行写入
  use_article_page: true      # 先抓取原文并抽取正文再交给 AI
  article_timeout_seconds: 15 # 抽取正文超时时间
  per_feed_limit: 1           # 单个源每次处理的最大条数（按时间倒序）

ai:                           # OpenAI 兼容接口
  enabled: true
  base_url: https://api.openai.com/v1
  api_key: YOUR_API_KEY
  model: glm-4.6
  temperature: 0.2
  system_prompt: |
    你是一个中文内容编辑助手。请对RSS文章进行信息抽取与高质量中文摘要，并输出严格的JSON对象，字段必须为：title, link, pubDate, author, summary_text。其中：title为原文标题或优化后的标题；link为原始URL；pubDate为发布时间（原文给出即可，若不是北京时间需转换）；author为作者（若未知可留空字符串）；summary_text为简洁、条理清晰的段落式中文总结。务必只输出JSON，不要任何解释或markdown。
  user_prompt_template: |
    标题: {title}
    链接: {link}
    发布时间: {pub_date}
    作者: {author}
    正文/摘要(可能包含HTML):
    {content}

    请只输出JSON，不要任何解释或markdown。

telegram:
  enabled: true
  bot_token: YOUR_TELEGRAM_BOT_TOKEN
  chat_id: "@your_channel_or_chat_id"
  push_summary: true          # 是否推送抓取汇总

reports:                      # 可选的周期汇总报告
  daily_enabled: true         # 每日汇总
  hourly_enabled: true        # 每小时汇总
  report_timeout_seconds: 60  # 调用 AI 生成报告的超时
  system_prompt: |            # 报告生成提示词，可自定义
    你是一名资深中文资讯编辑，需要汇总给定时间范围内的RSS内容。
    请输出结构化的纯文本报告，包含概览、重点事件、其余事件与数据统计。
  user_prompt_template: |
    请基于以下信息生成报告，输出时直接从“概览”部分开始，不要重复报告类型、时间范围或文章总数等字段。

    报告元信息：
    - 报告类型：{label}
    - 时间范围：{timeframe}
    - 文章总数：{article_count}

    来源统计：
    {feed_stats}

    文章详情（按时间排序）：
    {article_details}

logging:
  level: INFO
  file: logs/app.log
```

- AI 接口为 OpenAI 兼容格式（`/v1/chat/completions`），可自由替换 `base_url` 与 `model` 指向任意兼容服务。
- `fetch.filter_keywords` 支持中英文混排；英文匹配区分大小写，若需要字面量方括号请使用 YAML 字符串语法包裹。
- `reports` 模块会在抓取成功后按配置周期自动生成汇总文本，可结合 Telegram 推送或外部通知。
- 前端“设置”页支持在线更新上述配置。为安全起见，`api_key` 与 `bot_token` 在界面不回显；若不修改请留空，后端会保留旧值。
- 自定义提示词：
  - System Prompt 与 User Prompt 模板均可在前端“AI 设置”中修改并保存。
  - 若模板中需要字面量大括号，请使用双大括号进行转义，例如 `{{` 与 `}}`。

### 正文抽取说明

- 抽取逻辑基于启发式：优先选择 `<article>`、`<main>`、`#content`、`.content` 等容器，按段落数量与文本长度评分；会自动忽略 `script/style/nav/footer/aside` 等无关元素。
- 若抽取失败，会回退使用 RSS 内置的 `content/summary`。
- 可通过 `fetch.use_article_page` 开关控制是否启用该能力；超时由 `fetch.article_timeout_seconds` 控制。
- 每次抓取会先按时间倒序对条目排序，再截取 `fetch.per_feed_limit` 条进行处理，避免一次处理过多历史项。

## API 速览

- `GET /api/health` 健康检查
- `GET /api/settings` 获取配置（敏感信息打码）
- `PUT /api/settings` 更新配置（支持热更新抓取间隔）
- `POST /api/fetch` 立即抓取（可选 `{"force": false}`）
- `GET /api/articles?limit=20&offset=0&feed=` 列表查询
- `GET /api/articles/{id}` 文章详情

完整接口文档请见 `/docs`（Swagger UI）。

## 前端界面与操作

- 内容页工具栏
  - 自动刷新：每约 1 分钟自动刷新文章列表（调用 `GET /api/articles`）。仅更新前端显示，不会触发抓取、AI 调用或 Telegram 推送。
  - 强制抓取：勾选后点击“手动抓取”，向 `POST /api/fetch` 发送 `{"force": true}`。这会跳过前置去重检查，对候选条目执行“原文抽取 + AI 总结”。数据库仍有唯一约束，已存在的文章不会重复入库或再次推送；该操作会消耗 AI 调用，建议仅在联调/验证时使用。

- 设置页（要点）
  - 单源抓取上限：限制每次抓取时单个 RSS 源最多处理条数，按时间倒序优先（越新越先处理）。
  - 使用原文抽取正文 + 超时：先抓取原文网页并抽取正文，再交给 AI，总结质量更高；抽取失败则回退 RSS 摘要。
  - AI 提示词：内置默认 System Prompt 与 User Prompt 模板（已预填）；你可以直接微调而无需从零编写。

## 运行日志

- 统一输出到控制台与 `backend/logs/app.log`，日志包含抓取、去重、AI 调用与 Telegram 推送结果等信息，便于追踪问题。

## 去重与存储策略

- 基于 `(feed_url, item_uid)` 唯一约束进行去重。`item_uid` 优先使用 RSS 的 `id/guid` 字段；若缺失，则使用 `sha1(link|title)` 作为唯一标识。
- 存储超过 `max_items` 时自动删除最旧记录。


## 注意事项

- 首次运行前请在配置中填入有效的 AI `api_key` 与 `base_url`/`model`，以及 Telegram `bot_token` 与 `chat_id`（可选）。
- 网络环境受限时（例如公司内网），前端可本地打开使用；后端需要能访问 RSS、AI 接口与 Telegram。
- 本项目以稳定、可维护为目标，尽量减少外部依赖（存储使用 SQLite，调度器为内置线程）。
