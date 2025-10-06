# RSS‑AI

一个前后端分离的 RSS 助手：定时抓取多个 RSS 源，使用用户自定义的 AI（OpenAI 通用格式）对最新文章进行总结并排版，去重入库，推送到 Telegram 群组，同时提供标准 API 与前端 Web 管理界面。默认监听端口 `3601`。

– 后端：Python + FastAPI（含 OpenAPI/Swagger、详细日志、可热更新配置、后台定时任务）
– 前端：黑白配色、简约高级的 Web 页面（查看摘要与在线修改配置）

注意：本仓库为可直接运行的完整实现；首次运行会自动生成 `backend/config.yaml`。如需推送到 GitHub，请自行配置远程仓库与权限。

## 功能概览

- 定时抓取：从配置文件读取多个 RSS 源，按间隔抓取最新文章。
- AI 总结：调用用户配置的 OpenAI 兼容接口，输出 JSON，字段包含：
  - `title` 标题
  - `link` 原始网页 URL
  - `pubDate` 发布时间
  - `author` 作者
  - `summary_text` AI 中文总结
- 去重与存储：使用 SQLite 本地存储，基于 `feed_url + item_uid` 唯一约束去重；可配置最大存储条数，自动裁剪旧数据。
- Telegram 推送：将 AI 总结以精简排版推送到指定群组或频道。
- 标准 API：提供 RESTful 接口与 `/docs` Swagger UI。
- 前端管理：查看摘要列表、手动抓取、在线修改配置（无需重启服务）。

## 目录结构

- `backend/` 后端源码与依赖
  - `app/` FastAPI 应用、调度器、AI/Telegram 客户端、存储等模块
  - `config.example.yaml` 示例配置（首次运行会拷贝为 `config.yaml`）
  - `requirements.txt` 后端依赖
  - `run.sh` 启动脚本
- `frontend/` 前端静态页面（纯原生 HTML/CSS/JS，黑白配色）

## 快速开始

1) 准备环境

- Python 3.10+
- 可选：创建虚拟环境 `python -m venv .venv && source .venv/bin/activate`

2) 安装依赖并启动后端

```
cd backend
pip install -r requirements.txt
./run.sh
```

后端启动后监听 `http://127.0.0.1:3601`，Swagger UI 在 `http://127.0.0.1:3601/docs`。

3) 打开前端

直接用浏览器打开 `frontend/index.html` 即可。前端默认请求当前同源的后端 `/api/...` 接口，如需跨域部署，后端已启用 CORS（允许任意来源）。

## 配置说明（backend/config.yaml）

首次运行若不存在会自动从 `config.example.yaml` 生成。关键字段：

```
server:
  host: 0.0.0.0
  port: 3601

fetch:
  interval_minutes: 10   # 抓取间隔（分钟）
  max_items: 500         # 存储上限（总条数）
  feeds:                 # RSS 列表
    - https://hnrss.org/frontpage

ai:                      # OpenAI 通用格式
  enabled: true
  base_url: https://api.openai.com/v1
  api_key: YOUR_API_KEY
  model: gpt-4o-mini
  temperature: 0.2

telegram:
  enabled: false
  bot_token: YOUR_TELEGRAM_BOT_TOKEN
  chat_id: "@your_channel_or_chat_id"

logging:
  level: INFO
  file: logs/app.log
```

- AI 接口为 OpenAI 兼容格式（`/v1/chat/completions`），你可替换 `base_url` 与 `model` 指向任意兼容服务。
- 前端“设置”页支持在线更新以上配置。为安全起见，`api_key` 与 `bot_token` 在界面不回显；若不修改请留空，后端会保留旧值。

## API 速览

- `GET /api/health` 健康检查
- `GET /api/settings` 获取配置（敏感信息打码）
- `PUT /api/settings` 更新配置（支持热更新抓取间隔）
- `POST /api/fetch` 立即抓取（可选 `{"force": false}`）
- `GET /api/articles?limit=20&offset=0&feed=` 列表查询
- `GET /api/articles/{id}` 文章详情

完整接口文档请见 `/docs`（Swagger UI）。

## 运行日志

- 统一输出到控制台与 `backend/logs/app.log`，日志包含抓取、去重、AI 调用与 Telegram 推送结果等信息，便于追踪问题。

## 去重与存储策略

- 基于 `(feed_url, item_uid)` 唯一约束进行去重。`item_uid` 优先使用 RSS 的 `id/guid` 字段；若缺失，则使用 `sha1(link|title)` 作为唯一标识。
- 存储超过 `max_items` 时自动删除最旧记录。

## 部署建议

- 后端：可使用 `systemd`、`pm2` 或容器方式常驻运行；建议将 `backend/` 单独部署并暴露 3601 端口。
- 前端：纯静态资源，可托管在任意静态服务器或 CDN；若跨域部署，后端 CORS 已开放。

## 推送到 GitHub

本地完成后：

```
git init
git remote add origin git@github.com:<yourname>/rss-ai.git
git add .
git commit -m "feat: RSS-AI 初版"
git push -u origin main
```

如需我代为推送，请提供仓库写入权限或在当前环境开放网络访问权限。

## 注意事项

- 首次运行前请在配置中填入有效的 AI `api_key` 与 `base_url`/`model`，以及 Telegram `bot_token` 与 `chat_id`（可选）。
- 网络环境受限时（例如公司内网），前端可本地打开使用；后端需要能访问 RSS、AI 接口与 Telegram。
- 本项目以稳定、可维护为目标，尽量减少外部依赖（存储使用 SQLite，调度器为内置线程）。

## 许可证

本项目基于 MIT 许可发布。
