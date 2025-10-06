#!/usr/bin/env bash
set -euo pipefail
# 前端同源服务，默认监听 3602，并将 /api/* 反向代理到后端（默认 http://127.0.0.1:3601）

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

: "${PORT:=3602}"
: "${BACKEND_BASE_URL:=http://127.0.0.1:3601}"

echo "[frontend] serving at :$PORT -> proxy /api to ${BACKEND_BASE_URL}"
python server.py

