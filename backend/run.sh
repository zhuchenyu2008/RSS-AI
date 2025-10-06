#!/usr/bin/env bash
set -euo pipefail
export PYTHONUNBUFFERED=1
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

# Create default config if missing
if [ ! -f config.yaml ]; then
  cp config.example.yaml config.yaml
fi

mkdir -p logs data

# 使用应用内置的端口配置启动（server.port，默认3602）
python -m app.main
