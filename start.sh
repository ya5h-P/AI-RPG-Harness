#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LLM_PORT="${LLM_PORT:-8080}"
APP_PORT="${PORT:-7860}"
PID_FILE="$ROOT/.server.pid"

usage() {
  cat <<EOF
Usage: ./start.sh [command|options]

Commands:
  (default)        Start Web UI in foreground
  --tailscale      Also bind Tailscale IP so you can play from your phone
  --bg             Start in background (writes logs/server.log + .server.pid)
  status           Check LLM server and Web UI health + print URLs
  stop             Stop background Web UI server
  test             Run the unit test suite
  -h, --help       Show this help message

Options:
  Combine --bg with --tailscale (e.g. ./start.sh --bg --tailscale).
  Env vars: PORT (7860), HOST (127.0.0.1), LLM_URL (http://127.0.0.1:8080),
            LLM_PORT (8080)
EOF
}

cmd_status() {
  local llm_base="${LLM_URL:-http://127.0.0.1:${LLM_PORT}}"
  if curl -sf "${llm_base%/}/health" >/dev/null 2>&1 || curl -sf "${llm_base%/}/v1/models" >/dev/null 2>&1; then
    echo "LLM server   : RUNNING (${llm_base})"
  else
    echo "LLM server   : STOPPED (expected at ${llm_base})"
  fi
  if curl -sf "http://127.0.0.1:${APP_PORT}/api/llm/status" >/dev/null 2>&1; then
    echo "Web UI       : RUNNING (http://127.0.0.1:${APP_PORT})"
    if command -v tailscale >/dev/null 2>&1; then
      ts_ip=$(tailscale ip -4 2>/dev/null | head -n1 || true)
      if [[ -n "$ts_ip" ]]; then
        echo "Phone/TS URL : http://${ts_ip}:${APP_PORT}"
      fi
    fi
  else
    echo "Web UI       : STOPPED (port ${APP_PORT})"
  fi
}

cmd_stop() {
  local stopped=0
  if [[ -f "$PID_FILE" ]]; then
    pid="$(cat "$PID_FILE")"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      echo "Stopped Web UI (PID $pid)"
      stopped=1
    fi
    rm -f "$PID_FILE"
  fi
  local extra_pids
  extra_pids="$(ps -eo pid,args | awk -v p="$ROOT/server.py" 'index($0, p) && !/awk/ {print $1}')"
  if [[ -n "$extra_pids" ]]; then
    kill $extra_pids 2>/dev/null || true
    echo "Stopped Web UI"
    stopped=1
  fi
  if [[ "$stopped" -eq 0 ]]; then
    echo "No background Web UI running"
  fi
}

BG_MODE=0
SERVER_ARGS=()
for arg in "$@"; do
  case "$arg" in
    -h|--help|help)
      usage
      exit 0
      ;;
    status)
      cmd_status
      exit 0
      ;;
    stop)
      cmd_stop
      exit 0
      ;;
    test)
      cd "$ROOT"
      exec python3 -m unittest -v test_harness.py
      ;;
    --bg)
      BG_MODE=1
      ;;
    *)
      SERVER_ARGS+=("$arg")
      ;;
  esac
done

mkdir -p "$ROOT/logs"

if [[ "$BG_MODE" -eq 1 ]]; then
  cmd_stop >/dev/null 2>&1 || true
  nohup env PORT="$APP_PORT" python3 "$ROOT/server.py" "${SERVER_ARGS[@]}" >"$ROOT/logs/server.log" 2>&1 &
  echo $! >"$PID_FILE"
  sleep 0.6
  cmd_status
  echo "Logs: $ROOT/logs/server.log"
  exit 0
fi

echo "Starting AI RPG Harness web UI on port ${APP_PORT}..."
PORT="$APP_PORT" exec python3 "$ROOT/server.py" "${SERVER_ARGS[@]}"
