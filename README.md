# RSS-AI 项目说明

## 项目简介

**RSS‑AI** 是一个用于自动抓取多个 RSS 源、利用 AI 总结最新文章，并将整理后的内容推送到指定 Telegram 群组的系统。本项目采用前后端分离架构：后端使用 **Python + FastAPI**，前端为一个简洁的 Web 页面，黑白配色，简约高级。

核心特点：

* 支持配置多个 RSS 地址，定时抓取并检测新文章。
* 采用用户自定义的 AI 接口（例如 OpenAI）对文章内容进行中文总结并排版输出。
* 支持配置获取间隔、AI 模型、API 密钥、Telegram 机器人信息等。
* 推送到 Telegram 群组的消息包含：标题、链接、发布时间、作者以及 AI 总结内容。
* 前端界面可实时查看最近的摘要并在线修改配置，无需重启服务。

## 目录结构

```
rss-ai/
  backend/            后端服务源代码
    main.py           FastAPI 应用主程序
    config.json       默认配置文件，可通过前端修改
    requirements.txt  Python 依赖列表
    logs/             日志文件目录
    rss.db            SQLite 数据库（运行时生成）
  frontend/           前端静态页面
    index.html        前端入口页面
    main.js           与后端交互的脚本
    style.css         黑白配色样式表
  README.md           项目说明（当前文档）
```

## 安装与运行

以下操作假定您已安装好 **Python 3.9+** 和 **Node.js/npm** (如仅使用提供的简单前端，可不安装 Node)。

### 1. 后端

1. 进入 `backend` 目录安装依赖：

   ```bash
   cd rss-ai/backend
   python3 -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. 启动服务（默认监听 **3601** 端口）：

   ```bash
   uvicorn main:app --host 0.0.0.0 --port 3601
   ```

   启动后，后台任务会按照配置文件中的 `fetch_interval` 定时抓取 RSS。日志记录在 `backend/logs/rssai.log` 中。数据库位于 `backend/rss.db`。

### 2. 前端

本项目提供了一个简单的静态页面，直接通过浏览器打开即可。

1. 在 `frontend` 目录下启动一个静态文件服务器（可任选其一）：

   * 使用 Python：

     ```bash
     cd rss-ai/frontend
     python3 -m http.server 8080
     ```

     然后在浏览器访问 `http://localhost:8080/index.html`。

   * 或者将 `frontend` 目录部署到您喜欢的任意 Web 服务器。

2. 页面加载时会从 `/api/config` 获取后端配置，因此确保后端已经运行并允许跨域访问。

## 配置说明

配置文件位于 `backend/config.json`，在程序首次运行时会自动生成默认配置。亦可通过前端界面修改。

字段说明：

| 字段路径                | 说明                                       |
|-------------------------|--------------------------------------------|
| `rss_urls`              | RSS 源列表，每行为一个 RSS 地址             |
| `openai.api_key`        | AI 服务的密钥（必填）                       |
| `openai.api_base`       | AI 接口的 URL，可使用兼容 OpenAI 格式的接口 |
| `openai.model`          | AI 模型名称，如 `gpt-3.5-turbo`             |
| `telegram.token`        | Telegram 机器人 Token                      |
| `telegram.chat_id`      | 目标群组或频道的 ID（需机器人已加入群）     |
| `fetch_interval`        | 抓取间隔，单位为秒，最小 60 秒              |

修改配置后，后端会立即保存，并自动执行一次抓取任务；定时任务随后将按照新的间隔运行。

## 使用流程

1. 在前端页面中填写或修改 RSS 地址、AI 配置、Telegram 配置以及抓取间隔，并点击“保存设置”。
2. 点击“立即抓取”可以手动触发一次文章抓取及总结，通常用于调试或首次运行。
3. 稍等片刻即可在“最近摘要”列表中看到最新的总结内容，同时 Telegram 群组也会收到对应推送。

## 开发与定制

* 后端使用 **FastAPI**，易于扩展更多接口；如需调整日志格式、存储结构或引入其他 AI 模型，可在 `backend/main.py` 中修改。
* 前端采用原生 JavaScript，实现轻量且易于定制的交互逻辑；如需更复杂的界面，可以用 React/Vue 等框架替换。

## 免责声明

本项目仅用于学习和交流，使用者需自行遵守目标服务（如 OpenAI、Telegram 等）的使用条款。作者不对使用本项目产生的任何后果负责。