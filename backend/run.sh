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

python -m uvicorn app.main:app --host 0.0.0.0 --port 3601

