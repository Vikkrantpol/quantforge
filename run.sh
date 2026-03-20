#!/usr/bin/env bash
# QuantForge — Single-command launcher for macOS
# Usage: ./run.sh [--reset] [--backend-only] [--frontend-only]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
VENV_DIR="$ROOT/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
PID_FILE="$ROOT/.pids"
REQ_FILE="$BACKEND_DIR/requirements.txt"
REQ_STAMP="$VENV_DIR/.requirements.sha256"

BACKEND_PORT=8010
FRONTEND_PORT=5173

RESET=false
BACKEND_ONLY=false
FRONTEND_ONLY=false
CREATED_VENV=false

for arg in "$@"; do
  case $arg in
    --reset)         RESET=true ;;
    --backend-only)  BACKEND_ONLY=true ;;
    --frontend-only) FRONTEND_ONLY=true ;;
  esac
done

if command -v clear &>/dev/null; then
  clear 2>/dev/null || true
fi
echo ""
printf "${CYAN}${BOLD}"
echo "  ██████╗ ██╗   ██╗ █████╗ ███╗   ██╗████████╗███████╗ ██████╗ ██████╗  ██████╗ ███████╗"
echo "  ██╔═══██╗██║   ██║██╔══██╗████╗  ██║╚══██╔══╝██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝"
echo "  ██║   ██║██║   ██║███████║██╔██╗ ██║   ██║   █████╗  ██║   ██║██████╔╝██║  ███╗█████╗"
echo "  ██║▄▄ ██║██║   ██║██╔══██║██║╚██╗██║   ██║   ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝"
echo "  ╚██████╔╝╚██████╔╝██║  ██║██║ ╚████║   ██║   ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗"
echo "   ╚══▀▀═╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝   ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝"
printf "${NC}\n"
printf "${DIM}  Algorithmic Trading Research Platform — v1.0.0${NC}\n\n"

log()  { printf "${CYAN}  →${NC} %s\n" "$1"; }
ok()   { printf "${GREEN}  ✓${NC} %s\n" "$1"; }
warn() { printf "${YELLOW}  ⚠${NC} %s\n" "$1"; }
err()  { printf "${RED}  ✗${NC} %s\n" "$1"; }
step() { printf "\n${BOLD}${CYAN}[%s]${NC} %s\n" "$1" "$2"; }

get_listening_pid() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1
}

get_pid_cwd() {
  local pid="$1"
  lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1
}

stop_pid_tree() {
  local pid="$1"
  if [ -z "$pid" ]; then
    return
  fi

  pkill -P "$pid" 2>/dev/null || true
  kill "$pid" 2>/dev/null || true
}

clear_stale_listener() {
  local port="$1"
  local expected_cwd="$2"
  local label="$3"
  local pid
  pid="$(get_listening_pid "$port")"
  if [ -z "$pid" ]; then
    return 0
  fi

  local cwd
  cwd="$(get_pid_cwd "$pid")"
  if [ "$cwd" = "$expected_cwd" ]; then
    warn "Found stale ${label} listener on :${port} (PID ${pid}); cleaning it up"
    stop_pid_tree "$pid"
    sleep 1

    local remaining
    remaining="$(get_listening_pid "$port")"
    if [ -n "$remaining" ]; then
      warn "Listener on :${port} persisted after graceful stop; forcing PID ${remaining}"
      kill -9 "$remaining" 2>/dev/null || true
      sleep 1
    fi
    return 0
  fi

  err "Port ${port} is already in use by PID ${pid} (${cwd:-unknown cwd})"
  return 1
}

cleanup() {
  echo ""
  log "Shutting down all servers..."
  if [ -f "$PID_FILE" ]; then
    while IFS= read -r pid; do
      stop_pid_tree "$pid"
      ok "Stopped PID $pid"
    done < "$PID_FILE"
    rm -f "$PID_FILE"
  fi
  printf "${GREEN}  Goodbye!${NC}\n\n"
}
trap cleanup EXIT INT TERM

# ─── Prerequisites ───────────────────────────────────────────
step "1/5" "Checking prerequisites"

if ! command -v python3 &>/dev/null; then
  err "python3 not found. Install from https://python.org (3.10+)"
  exit 1
fi
PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
ok "Python $PYVER"

if ! command -v node &>/dev/null; then
  err "Node.js not found. Install from https://nodejs.org (v18+)"
  exit 1
fi
ok "Node $(node --version)"

# ─── Venv ────────────────────────────────────────────────────
step "2/5" "Python virtual environment"

if $RESET; then
  warn "--reset: removing existing venv and node_modules"
  rm -rf "$VENV_DIR" "$FRONTEND_DIR/node_modules"
fi

if [ ! -d "$VENV_DIR" ]; then
  log "Creating virtualenv at .venv ..."
  python3 -m venv "$VENV_DIR"
  CREATED_VENV=true
fi

if [ ! -x "$VENV_PYTHON" ]; then
  err "Virtualenv Python not found at $VENV_PYTHON"
  err "Run ./run.sh --reset to recreate the environment"
  exit 1
fi

source "$VENV_DIR/bin/activate"
ok "Activated virtualenv"

REQ_HASH="$(shasum -a 256 "$REQ_FILE" | awk '{print $1}')"
CURRENT_REQ_HASH=""
if [ -f "$REQ_STAMP" ]; then
  CURRENT_REQ_HASH="$(cat "$REQ_STAMP")"
fi

verify_python_env() {
  "$VENV_PYTHON" - <<'PY' >/dev/null
import importlib

required = [
    "fastapi",
    "uvicorn",
    "pandas",
    "numpy",
    "yfinance",
    "httpx",
    "dotenv",
    "fyers_apiv3",
]

for module in required:
    importlib.import_module(module)
PY
}

if $CREATED_VENV || [ "$CURRENT_REQ_HASH" != "$REQ_HASH" ]; then
  log "Installing Python dependencies (this may take 60s on first run)..."
  "$VENV_PYTHON" -m pip install --upgrade pip -q || warn "pip upgrade skipped"
  if "$VENV_PYTHON" -m pip install -r "$REQ_FILE" -q; then
    printf "%s\n" "$REQ_HASH" > "$REQ_STAMP"
    ok "Python packages installed"
  else
    warn "Dependency install failed; checking existing virtualenv packages..."
    if verify_python_env; then
      printf "%s\n" "$REQ_HASH" > "$REQ_STAMP"
      warn "Using already-installed Python packages from the current virtualenv"
    else
      rm -f "$REQ_STAMP"
      err "Python dependency install failed and the current virtualenv is incomplete"
      err "Run ./run.sh --reset after restoring network access"
      exit 1
    fi
  fi
else
  ok "Python packages already synced"
fi

# ─── Sample data ─────────────────────────────────────────────
step "3/5" "Sample OHLCV data"

if [ ! -f "$BACKEND_DIR/data/AAPL_sample.csv" ]; then
  log "Generating GBM sample data (7 symbols × 5 years)..."
  cd "$BACKEND_DIR" && python3 generate_sample_data.py
  ok "Sample data ready"
else
  ok "Sample data already present"
fi

# ─── Frontend ────────────────────────────────────────────────
step "4/5" "Frontend dependencies"

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  log "Running npm install in frontend/ ..."
  cd "$FRONTEND_DIR" && npm install --silent
  ok "npm packages installed"
else
  ok "node_modules present"
fi

# ─── Start ───────────────────────────────────────────────────
step "5/5" "Starting servers"
> "$PID_FILE"

if ! $FRONTEND_ONLY; then
  clear_stale_listener "$BACKEND_PORT" "$BACKEND_DIR" "QuantForge backend" || exit 1
  log "Starting FastAPI backend on :$BACKEND_PORT ..."
  cd "$BACKEND_DIR"
  PYTHONPATH="$ROOT" "$VENV_PYTHON" -m uvicorn main:app \
    --host 127.0.0.1 \
    --port "$BACKEND_PORT" \
    --reload \
    --log-level warning &
  BACKEND_PID=$!
  echo "$BACKEND_PID" >> "$PID_FILE"
  sleep 2

  if kill -0 "$BACKEND_PID" 2>/dev/null; then
    ok "Backend  → http://localhost:$BACKEND_PORT"
    ok "API docs → http://localhost:$BACKEND_PORT/docs"
  else
    err "Backend failed to start. Run: cd backend && uvicorn main:app --reload"
    exit 1
  fi
fi

if ! $BACKEND_ONLY; then
  clear_stale_listener "$FRONTEND_PORT" "$FRONTEND_DIR" "QuantForge frontend" || exit 1
  log "Starting Vite frontend on :$FRONTEND_PORT ..."
  cd "$FRONTEND_DIR"
  npm run dev -- --port "$FRONTEND_PORT" --host &
  FRONTEND_PID=$!
  echo "$FRONTEND_PID" >> "$PID_FILE"
  sleep 4

  if kill -0 "$FRONTEND_PID" 2>/dev/null; then
    ok "Frontend → http://localhost:$FRONTEND_PORT"
  else
    err "Frontend failed to start. Run: cd frontend && npm run dev"
    exit 1
  fi
fi

echo ""
printf "${GREEN}${BOLD}"
echo "  ┌─────────────────────────────────────────────┐"
echo "  │            QuantForge is running!           │"
echo "  │                                             │"
printf "  │  UI:       http://localhost:%-5s           │\n" "$FRONTEND_PORT"
printf "  │  API:      http://localhost:%-5s           │\n" "$BACKEND_PORT"
printf "  │  API Docs: http://localhost:%s/docs       │\n" "$BACKEND_PORT"
echo "  │                                             │"
echo "  │  Ctrl+C to stop all servers                 │"
echo "  └─────────────────────────────────────────────┘"
printf "${NC}\n"

# Auto-open browser on macOS
if ! $BACKEND_ONLY && [[ "$OSTYPE" == "darwin"* ]] && command -v open &>/dev/null; then
  sleep 2 && open "http://localhost:$FRONTEND_PORT" &
fi

wait
