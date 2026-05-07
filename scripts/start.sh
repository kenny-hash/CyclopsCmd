#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
SKIP_INSTALL="${SKIP_INSTALL:-0}"

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if [[ "$SKIP_INSTALL" != "1" ]]; then
  python -m pip install --upgrade pip
  python -m pip install -r backend/requirements.txt

  if [[ ! -d node_modules ]]; then
    npm install
  fi
fi

export VITE_BACKEND_TARGET="${VITE_BACKEND_TARGET:-http://${BACKEND_HOST}:${BACKEND_PORT}}"
export VITE_BACKEND_WS_HOST="${VITE_BACKEND_WS_HOST:-${BACKEND_HOST}}"
export VITE_BACKEND_WS_PORT="${VITE_BACKEND_WS_PORT:-${BACKEND_PORT}}"

echo "Starting CyclopsCmd backend at http://${BACKEND_HOST}:${BACKEND_PORT}"
uvicorn app:app --app-dir backend --host "$BACKEND_HOST" --port "$BACKEND_PORT" &
BACKEND_PID=$!

echo "Starting CyclopsCmd frontend at http://${FRONTEND_HOST}:${FRONTEND_PORT}"
npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" &
FRONTEND_PID=$!

echo
cat <<INFO
CyclopsCmd is starting:
  Frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}
  Backend:  http://${BACKEND_HOST}:${BACKEND_PORT}

Press Ctrl+C to stop both services.
INFO

wait -n "$BACKEND_PID" "$FRONTEND_PID"
