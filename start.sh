#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname "$0")" >/dev/null 2>&1 && pwd)"

# 启动后端 (后台)
echo "正在启动后端服务..."
(cd "$ROOT_DIR/backend" && uv run uvicorn main:app --host 0.0.0.0 --port 8000) &
BACKEND_PID=$!
trap 'echo "正在关闭后端服务..."; kill $BACKEND_PID 2>/dev/null || true' EXIT
echo "后端服务已启动 (PID: $BACKEND_PID)"

# 启动前端 (前台)
echo "正在启动前端服务..."
cd "$ROOT_DIR/frontend"
uv run streamlit run app.py
