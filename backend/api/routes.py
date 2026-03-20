"""
routes.py
All REST API endpoints for the trading research platform.
"""

import os
import uuid
import threading
import time
from typing import Optional, Dict, Any
from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from backend.modules.metrics_engine import compute_all_metrics
from backend.modules.broker_connector import (
    validate_broker as _validate_broker,
    generate_fyers_auth_url,
    exchange_fyers_auth_code,
    normalize_fyers_access_token,
)
from backend.modules.data_ingestion import load_data, load_from_yfinance, resolve_period
from backend.modules.history_manager import save_backtest, get_history, get_backtest_details
from backend.modules.strategy_engine import run_strategy
from backend.modules.backtest_engine import run_backtest
import config
from fastapi import File, UploadFile

router = APIRouter(prefix="/api")

# ─────────────────────────────────────────────────────────────
# In-memory task store
# ─────────────────────────────────────────────────────────────
_tasks: Dict[str, Dict] = {}  # task_id -> {status, logs, progress, results, error}
_LOCALHOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _new_task() -> str:
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {
        "status": "running",
        "logs": [],
        "progress": 0,
        "results": None,
        "error": None,
        "created_at": datetime.utcnow().isoformat(),
    }
    return task_id


def _is_local_request(request: Request) -> bool:
    host = getattr(getattr(request, "client", None), "host", "") or ""
    return host in _LOCALHOSTS or host.startswith("127.")


def _assert_local_broker_access(request: Request):
    if _is_local_request(request):
        return
    raise HTTPException(403, "Broker and server-side credential endpoints are restricted to localhost for security.")


def _log(task_id: str, msg: str, progress: int = None):
    ts = datetime.utcnow().strftime("%H:%M:%S.%f")[:-3]
    entry = f"[{ts}] {msg}"
    _tasks[task_id]["logs"].append(entry)
    if progress is not None:
        _tasks[task_id]["progress"] = progress


def _fail(task_id: str, error: str):
    _tasks[task_id]["status"] = "error"
    _tasks[task_id]["error"] = error
    _log(task_id, f"ERROR: {error}")


def _complete(task_id: str, results: Any):
    _tasks[task_id]["status"] = "complete"
    _tasks[task_id]["results"] = results
    _tasks[task_id]["progress"] = 100


# ─────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    symbol: str = "AAPL"
    start: str = "2021-01-01"
    end: str = "2024-01-01"
    interval: str = "1d"
    source: str = "yfinance"   # yfinance | csv | broker
    csv_path: Optional[str] = None
    broker: Optional[str] = None
    broker_api_key: Optional[str] = None
    broker_secret_key: Optional[str] = None
    strategy: str = "ema_crossover"
    strategy_params: Dict[str, Any] = {}
    initial_capital: float = 100_000.0
    slippage_pct: float = 0.05
    commission: float = 10.0
    position_sizing: str = "pct_capital"
    position_pct: float = 20.0
    fixed_units: int = 100
    stop_loss_pct: Optional[float] = None
    stop_loss_atr_mult: Optional[float] = None
    execution_mode: str = "on_close"
    period: Optional[str] = None
    risk_free_rate: float = 0.05


class DownloadRequest(BaseModel):
    symbol: str = "AAPL"
    start: str = "2022-01-01"
    end: str = "2024-01-01"
    interval: str = "1d"
    source: str = "yfinance"
    broker: Optional[str] = None
    broker_api_key: Optional[str] = None
    broker_secret_key: Optional[str] = None


class BrokerValidateRequest(BaseModel):
    broker: str
    api_key: str
    secret_key: str
    base_url: Optional[str] = ""


class FyersLoginUrlRequest(BaseModel):
    api_key: Optional[str] = ""
    app_secret: Optional[str] = ""
    redirect_uri: Optional[str] = ""
    state: Optional[str] = ""


class FyersTokenExchangeRequest(BaseModel):
    auth_code: str
    api_key: Optional[str] = ""
    app_secret: Optional[str] = ""
    redirect_uri: Optional[str] = ""


class FyersSaveSessionRequest(BaseModel):
    api_key: Optional[str] = ""
    app_secret: Optional[str] = ""
    redirect_uri: Optional[str] = ""
    access_token: str


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}***{value[-3:]}"


def _reload_runtime_config():
    config.reload_settings()


def _is_valid_fyers_redirect_uri(redirect_uri: str) -> bool:
    if not redirect_uri:
        return False

    parsed = urlparse(redirect_uri)
    return bool(parsed.scheme and parsed.netloc and parsed.path.rstrip("/") == "/broker/fyers/callback")


def _is_absolute_http_url(value: str) -> bool:
    if not value:
        return False

    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _write_env_updates(updates: Dict[str, str]):
    env_path = config.ENV_FILE
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()

    pending = dict(updates)
    rendered = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            rendered.append(line)
            continue

        key, _, _ = line.partition("=")
        env_key = key.strip()
        if env_key in pending:
            rendered.append(f"{env_key}={pending.pop(env_key)}")
        else:
            rendered.append(line)

    if pending:
        if rendered and rendered[-1] != "":
            rendered.append("")
        for key, value in pending.items():
            rendered.append(f"{key}={value}")

    with open(env_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(rendered).rstrip() + "\n")


def _apply_runtime_env(updates: Dict[str, str]):
    for key, value in updates.items():
        os.environ[key] = value

    if "FYERS_APP_ID" in updates:
        config.FYERS_APP_ID = updates["FYERS_APP_ID"]
    if "FYERS_SECRET_KEY" in updates:
        config.FYERS_SECRET_KEY = updates["FYERS_SECRET_KEY"]
    if "FYERS_REDIRECT_URI" in updates:
        config.FYERS_REDIRECT_URI = updates["FYERS_REDIRECT_URI"]
    if "FYERS_ACCESS_TOKEN" in updates:
        config.FYERS_ACCESS_TOKEN = updates["FYERS_ACCESS_TOKEN"]


def _resolve_broker_credentials(
    broker: Optional[str],
    api_key: Optional[str] = "",
    secret_key: Optional[str] = "",
    base_url: Optional[str] = "",
) -> tuple[str, str, str]:
    _reload_runtime_config()
    broker = (broker or "").lower()
    api_key = api_key or ""
    secret_key = secret_key or ""
    base_url = base_url or ""

    if broker == "alpaca":
        return (
            api_key or config.ALPACA_API_KEY,
            secret_key or config.ALPACA_SECRET_KEY,
            base_url or config.ALPACA_BASE_URL,
        )
    if broker == "zerodha":
        return (
            api_key or config.KITE_API_KEY,
            secret_key or config.KITE_ACCESS_TOKEN,
            base_url,
        )
    if broker == "fyers":
        return (
            api_key or config.FYERS_APP_ID,
            secret_key or config.FYERS_ACCESS_TOKEN,
            base_url,
        )

    return api_key, secret_key, base_url


def _resolve_fyers_auth_settings(
    api_key: Optional[str] = "",
    app_secret: Optional[str] = "",
    redirect_uri: Optional[str] = "",
) -> tuple[str, str, str]:
    _reload_runtime_config()
    return (
        api_key or config.FYERS_APP_ID,
        app_secret or config.FYERS_SECRET_KEY,
        redirect_uri or config.FYERS_REDIRECT_URI,
    )


def _persist_fyers_settings(
    api_key: str,
    app_secret: str,
    redirect_uri: str,
    access_token: str,
):
    updates = {
        "FYERS_APP_ID": api_key,
        "FYERS_SECRET_KEY": app_secret,
        "FYERS_REDIRECT_URI": redirect_uri,
        "FYERS_ACCESS_TOKEN": access_token,
    }
    _write_env_updates(updates)
    _apply_runtime_env(updates)


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@router.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat(), "version": "1.0.0"}


@router.get("/symbols")
def get_symbols():
    return {
        "us": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "SPY", "QQQ", "GLD"],
        "india": ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "WIPRO.NS"],
        "crypto": ["BTC-USD", "ETH-USD", "SOL-USD"],
        "indices": ["^NSEI", "^GSPC", "^DJI", "^IXIC"],
    }


# ────── Backtest ──────

def _run_backtest_task(task_id: str, req: BacktestRequest):
    try:
        log = lambda msg, p=None: _log(task_id, msg, p)

        log(f"Initializing backtest for {req.symbol} | {req.strategy}", 5)
        time.sleep(0.1)

        # 1. Resolve period if provided
        start_date = req.start
        end_date = req.end
        if req.period:
            start_date, end_date = resolve_period(req.period)
            log(f"Resolved period '{req.period}' to {start_date} → {end_date}")

        # 2. Load data
        log(f"Fetching OHLCV data from {req.source.upper()}...", 10)
        broker_api_key, broker_secret_key, _ = _resolve_broker_credentials(
            req.broker,
            req.broker_api_key,
            req.broker_secret_key,
        )
        df = load_data(
            source=req.source,
            symbol=req.symbol,
            start=start_date,
            end=end_date,
            interval=req.interval,
            csv_path=req.csv_path,
            broker=req.broker,
            api_key=broker_api_key,
            secret_key=broker_secret_key,
            log_fn=log,
        )
        if df.empty:
            raise ValueError("No data returned for the selected symbol, date range, and interval.")
        log(f"Loaded {len(df)} bars | {df.index[0].date()} → {df.index[-1].date()}", 25)

        # 2. Run strategy
        log(f"Running strategy: {req.strategy} with params {req.strategy_params}", 35)
        df_signals = run_strategy(
            df,
            req.strategy,
            req.strategy_params,
            execution_mode=req.execution_mode,
            log_fn=log,
        )
        signal_count = (df_signals["signal"] != 0).sum()
        log(f"Generated {signal_count} signals", 50)

        # 3. Backtest
        log(f"Simulating trades | slippage={req.slippage_pct}% | execution={req.execution_mode}", 60)
        bt_result = run_backtest(
            df=df_signals,
            initial_capital=req.initial_capital,
            slippage_pct=req.slippage_pct,
            commission=req.commission,
            execution_mode=req.execution_mode,
            position_sizing=req.position_sizing,
            position_pct=req.position_pct,
            fixed_units=req.fixed_units,
            stop_loss_pct=req.stop_loss_pct,
            stop_loss_atr_mult=req.stop_loss_atr_mult,
            log_fn=log,
        )
        log(f"Backtest done | {bt_result['total_trades']} trades", 75)

        # 4. Metrics
        log("Computing performance metrics...", 85)
        metrics = compute_all_metrics(
            equity_curve=bt_result["equity_curve"],
            trades=bt_result["trades"],
            initial_capital=req.initial_capital,
            final_value=bt_result["final_value"],
            risk_free_rate=req.risk_free_rate,
        )
        log(
            f"CAGR: {metrics['cagr_pct']:.2f}% | Sharpe: {metrics['sharpe_ratio']:.2f} | "
            f"Max DD: {metrics['max_drawdown_pct']:.2f}% | Win Rate: {metrics['win_rate']:.1f}%",
            95
        )

        # Build indicator data for chart overlays
        indicator_cols = [c for c in df_signals.columns if c not in {"open", "high", "low", "close", "volume", "signal", "position"}]
        indicator_data = {}
        for col in indicator_cols:
            indicator_data[col] = [
                {"date": str(d.date() if hasattr(d, 'date') else d), "value": round(float(v), 4)}
                for d, v in df_signals[col].dropna().items()
            ]

        results = {
            "symbol": req.symbol,
            "strategy": req.strategy,
            "strategy_params": req.strategy_params,
            "interval": req.interval,
            "start": req.start,
            "end": req.end,
            "metrics": metrics,
            "equity_curve": bt_result["equity_curve"],
            "trades": bt_result["trades"],
            "drawdown_series": metrics.pop("drawdown_series"),
            "indicator_data": indicator_data,
            "total_bars": len(df),
            "execution_mode": req.execution_mode,
        }

        # 5. Save to history
        try:
            save_backtest(task_id, results)
            log("Saved results to history.", 98)
        except Exception as he:
            log(f"Warning: Failed to save to history: {he}")

        log("All done. Results ready!", 100)
        _complete(task_id, results)

    except ValueError as e:
        _fail(task_id, str(e))
    except Exception as e:
        import traceback
        _fail(task_id, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


@router.post("/backtest")
def start_backtest(req: BacktestRequest, request: Request):
    if req.source == "broker" or req.broker:
        _assert_local_broker_access(request)
    task_id = _new_task()
    t = threading.Thread(target=_run_backtest_task, args=(task_id, req), daemon=True)
    t.start()
    return {"backtest_id": task_id}


@router.get("/backtest/{task_id}/status")
def get_backtest_status(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(404, "Backtest not found")
    task = _tasks[task_id]
    return {
        "status": task["status"],
        "logs": task["logs"],
        "progress": task["progress"],
        "error": task["error"],
    }


@router.get("/backtest/{task_id}/results")
def get_backtest_results(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(404, "Backtest not found")
    task = _tasks[task_id]
    if task["status"] != "complete":
        raise HTTPException(400, f"Backtest status: {task['status']}")
    return task["results"]


# ────── Download Data ──────

def _run_download_task(task_id: str, req: DownloadRequest):
    try:
        log = lambda msg, p=None: _log(task_id, msg, p)
        log(f"Starting download: {req.symbol} | {req.interval} | {req.start}→{req.end}", 10)

        broker_api_key, broker_secret_key, _ = _resolve_broker_credentials(
            req.broker,
            req.broker_api_key,
            req.broker_secret_key,
        )
        df = load_data(
            source=req.source,
            symbol=req.symbol,
            start=req.start,
            end=req.end,
            interval=req.interval,
            broker=req.broker,
            api_key=broker_api_key,
            secret_key=broker_secret_key,
            log_fn=log,
        )

        log(f"Downloaded {len(df)} bars for {req.symbol}", 80)

        # Save to temp CSV
        filename = f"{req.symbol}_{req.interval}_{req.start}_{req.end}.csv".replace(":", "-")
        filepath = os.path.join(config.TEMP_DIR, filename)
        df.to_csv(filepath)
        log(f"Saved to {filename}", 95)

        _complete(task_id, {
            "filename": filename,
            "filepath": filepath,
            "rows": len(df),
            "columns": list(df.columns),
            "symbol": req.symbol,
            "interval": req.interval,
        })
        log("Download complete!", 100)

    except Exception as e:
        _fail(task_id, str(e))


@router.post("/download-data")
def start_download(req: DownloadRequest, request: Request):
    if req.source == "broker" or req.broker:
        _assert_local_broker_access(request)
    task_id = _new_task()
    t = threading.Thread(target=_run_download_task, args=(task_id, req), daemon=True)
    t.start()
    return {"download_id": task_id}


@router.get("/download-data/{task_id}/status")
def get_download_status(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(404, "Download task not found")
    task = _tasks[task_id]
    return {
        "status": task["status"],
        "logs": task["logs"],
        "progress": task["progress"],
        "error": task["error"],
        "result": task.get("results"),
    }


@router.get("/download-data/{task_id}/csv")
def download_csv(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(404, "Download task not found")
    task = _tasks[task_id]
    if task["status"] != "complete":
        raise HTTPException(400, "Download not complete yet")

    filepath = task["results"]["filepath"]
    filename = task["results"]["filename"]

    if not os.path.exists(filepath):
        raise HTTPException(404, "File not found on disk")

    def iter_file():
        with open(filepath, "rb") as f:
            yield from f

    return StreamingResponse(
        iter_file(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ────── Broker ──────

@router.post("/validate-broker")
def validate_broker_endpoint(req: BrokerValidateRequest, request: Request):
    _assert_local_broker_access(request)
    api_key, secret_key, base_url = _resolve_broker_credentials(
        req.broker,
        req.api_key,
        req.secret_key,
        req.base_url,
    )
    result = _validate_broker(req.broker, api_key, secret_key, base_url)
    return result


@router.get("/broker/defaults")
def get_broker_defaults(request: Request):
    _assert_local_broker_access(request)
    _reload_runtime_config()
    return {
        "alpaca": {
            "has_api_key": bool(config.ALPACA_API_KEY),
            "has_secret_key": bool(config.ALPACA_SECRET_KEY),
            "base_url": config.ALPACA_BASE_URL,
            "api_key_hint": _mask_secret(config.ALPACA_API_KEY),
        },
        "zerodha": {
            "has_api_key": bool(config.KITE_API_KEY),
            "has_access_token": bool(config.KITE_ACCESS_TOKEN),
            "api_key_hint": _mask_secret(config.KITE_API_KEY),
        },
        "fyers": {
            "has_api_key": bool(config.FYERS_APP_ID),
            "has_secret_key": bool(config.FYERS_SECRET_KEY),
            "has_access_token": bool(config.FYERS_ACCESS_TOKEN),
            "redirect_uri": config.FYERS_REDIRECT_URI,
            "redirect_uri_absolute": _is_absolute_http_url(config.FYERS_REDIRECT_URI),
            "redirect_uri_valid": _is_valid_fyers_redirect_uri(config.FYERS_REDIRECT_URI),
            "api_key_hint": _mask_secret(config.FYERS_APP_ID),
            "access_token_hint": _mask_secret(config.FYERS_ACCESS_TOKEN),
            "auth_ready": bool(
                config.FYERS_APP_ID and
                config.FYERS_SECRET_KEY and
                _is_absolute_http_url(config.FYERS_REDIRECT_URI)
            ),
        },
    }


@router.post("/broker/fyers/login-url")
def create_fyers_login_url(req: FyersLoginUrlRequest, request: Request):
    _assert_local_broker_access(request)
    api_key, app_secret, redirect_uri = _resolve_fyers_auth_settings(
        req.api_key,
        req.app_secret,
        req.redirect_uri,
    )
    if not api_key or not app_secret or not redirect_uri:
        raise HTTPException(400, "FYERS App ID, Secret ID, and Redirect URL are required. Set them in .env or enter them in the dashboard.")
    if not _is_absolute_http_url(redirect_uri):
        raise HTTPException(400, "FYERS Redirect URL must be a valid absolute http/https URL.")

    state = req.state or f"quantforge-{uuid.uuid4().hex[:10]}"
    auth_url = generate_fyers_auth_url(api_key, app_secret, redirect_uri, state)
    return {
        "broker": "fyers",
        "auth_url": auth_url,
        "state": state,
        "redirect_uri": redirect_uri,
    }


@router.post("/broker/fyers/exchange-token")
def fyers_exchange_token(req: FyersTokenExchangeRequest, request: Request):
    _assert_local_broker_access(request)
    api_key, app_secret, redirect_uri = _resolve_fyers_auth_settings(
        req.api_key,
        req.app_secret,
        req.redirect_uri,
    )
    if not api_key or not app_secret or not redirect_uri:
        raise HTTPException(400, "FYERS App ID, Secret ID, and Redirect URL are required. Set them in .env or enter them in the dashboard.")
    if not _is_absolute_http_url(redirect_uri):
        raise HTTPException(400, "FYERS Redirect URL must be a valid absolute http/https URL.")
    if not req.auth_code:
        raise HTTPException(400, "FYERS auth_code is required.")

    return exchange_fyers_auth_code(api_key, app_secret, redirect_uri, req.auth_code)


@router.post("/broker/fyers/save-session")
def save_fyers_session(req: FyersSaveSessionRequest, request: Request):
    _assert_local_broker_access(request)
    api_key, app_secret, redirect_uri = _resolve_fyers_auth_settings(
        req.api_key,
        req.app_secret,
        req.redirect_uri,
    )
    access_token = normalize_fyers_access_token(api_key, req.access_token)

    if not api_key:
        raise HTTPException(400, "FYERS App ID is required to save the session.")
    if not app_secret:
        raise HTTPException(400, "FYERS Secret ID is required to save the session.")
    if not access_token:
        raise HTTPException(400, "FYERS access token is required.")
    if not redirect_uri or not _is_absolute_http_url(redirect_uri):
        raise HTTPException(400, "FYERS Redirect URL must be a valid absolute http/https URL.")

    _persist_fyers_settings(api_key, app_secret, redirect_uri, access_token)
    return {
        "status": "ok",
        "broker": "fyers",
        "saved": True,
        "redirect_uri": redirect_uri,
        "access_token_hint": _mask_secret(access_token),
        "callback_ready": _is_valid_fyers_redirect_uri(redirect_uri),
    }


# ────── Sample data info ──────

@router.get("/sample-data")
def list_sample_data():
    data_dir = config.DATA_DIR
    files = []
    if os.path.exists(data_dir):
        for f in os.listdir(data_dir):
            if f.endswith(".csv"):
                path = os.path.join(data_dir, f)
                files.append({"filename": f, "path": path, "size_kb": round(os.path.getsize(path) / 1024, 1)})
    return {"files": files}


@router.get("/sample-data/{filename}")
def download_sample_data(filename: str):
    path = os.path.join(config.DATA_DIR, filename)
    if not os.path.exists(path) or not filename.endswith(".csv"):
        raise HTTPException(404, "Sample file not found")
        
    def iter_file():
        with open(path, "rb") as f:
            yield from f
            
    return StreamingResponse(
        iter_file(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only CSV files are allowed")
        
    os.makedirs(config.DATA_DIR, exist_ok=True)
    filename = f"upload_{int(time.time())}_{file.filename}"
    path = os.path.join(config.DATA_DIR, filename)
    
    with open(path, "wb") as f:
        content = await file.read()
        f.write(content)
        
    return {"filename": filename, "path": path, "message": "File uploaded successfully"}


@router.get("/history")
def list_history(limit: int = Query(50)):
    return {"history": get_history(limit)}


@router.get("/history/{task_id}")
def history_details(task_id: str):
    result = get_backtest_details(task_id)
    if not result:
        raise HTTPException(404, "History item not found")
    return {"result": result}
