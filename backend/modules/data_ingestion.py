"""
data_ingestion.py
Handles OHLCV data loading from CSV files, yfinance, or broker APIs.
"""

import os
import importlib
import io
import logging
import pandas as pd
import numpy as np
import httpx
from typing import Optional, Callable
from datetime import datetime
from contextlib import redirect_stdout, redirect_stderr
import config


TIMEFRAME_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "1d": "1d",
    "1wk": "1wk",
    "1mo": "1mo",
}

REQUIRED_COLS = {"open", "high", "low", "close", "volume"}
YFINANCE_INTRADAY_LOOKBACK_DAYS = {
    # Use a 1-day safety buffer because exact boundary requests can return
    # empty data even when they nominally match Yahoo's documented limits.
    "1m": 59,
    "2m": 59,
    "5m": 59,
    "15m": 59,
    "30m": 59,
    "60m": 729,
    "90m": 59,
    "1h": 729,
}

YFINANCE_CACHE_DIR = os.path.join(config.DATA_DIR, "yfinance_cache")


def _load_from_yahoo_chart_api(
    symbol: str,
    start: str,
    end: str,
    interval: str,
    log_fn: Optional[Callable] = None,
) -> pd.DataFrame:
    start_dt = pd.to_datetime(start, errors="coerce")
    end_dt = pd.to_datetime(end, errors="coerce")
    if pd.isna(start_dt) or pd.isna(end_dt):
        raise ValueError("Invalid start/end date for Yahoo chart API request.")

    start_ts = int(start_dt.tz_localize("UTC").timestamp())
    end_ts = int(end_dt.tz_localize("UTC").timestamp())
    if end_ts <= start_ts:
        raise ValueError("End date must be after start date for Yahoo chart API request.")

    params = {
        "period1": start_ts,
        "period2": end_ts,
        "interval": interval,
        "includePrePost": "false",
        "events": "div,splits",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 QuantForge/1.0",
        "Accept": "application/json,text/plain,*/*",
    }

    if log_fn:
        log_fn(f"[yfinance] Querying Yahoo chart API for {symbol}")

    response = httpx.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params=params,
        headers=headers,
        timeout=20.0,
        follow_redirects=True,
    )
    response.raise_for_status()

    payload = response.json()
    chart = (payload or {}).get("chart", {})
    error = chart.get("error")
    if error:
        raise ValueError(error.get("description") or error.get("code") or "Yahoo chart API returned an error")

    results = chart.get("result") or []
    if not results:
        raise ValueError("Yahoo chart API returned no result set")

    result = results[0]
    timestamps = result.get("timestamp") or []
    quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    if not timestamps or not quotes:
        raise ValueError("Yahoo chart API returned no candle data")

    df = pd.DataFrame({
        "Date": pd.to_datetime(timestamps, unit="s", utc=True),
        "open": quotes.get("open", []),
        "high": quotes.get("high", []),
        "low": quotes.get("low", []),
        "close": quotes.get("close", []),
        "volume": quotes.get("volume", []),
    })

    adjclose = (((result.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose")
    if adjclose:
        adjclose = pd.Series(adjclose, dtype="float64")
        close = pd.Series(df["close"], dtype="float64")
        factor = np.where(close.notna() & (close != 0), adjclose / close, np.nan)
        for col in ["open", "high", "low"]:
            df[col] = pd.Series(df[col], dtype="float64") * factor
        df["close"] = adjclose

    timezone = (result.get("meta") or {}).get("exchangeTimezoneName")
    if timezone:
        try:
            df["Date"] = df["Date"].dt.tz_convert(timezone)
        except Exception:
            pass

    df["Date"] = df["Date"].dt.tz_localize(None)
    df = df.set_index("Date")
    return df


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names to lowercase and standardize Date index."""
    df.columns = [c.strip().lower() for c in df.columns]
    # Handle 'adj close' → 'close'
    if "adj close" in df.columns and "close" not in df.columns:
        df = df.rename(columns={"adj close": "close"})
    if "adj close" in df.columns:
        df = df.drop(columns=["adj close"])
    # Ensure Date is index
    if "date" in df.columns:
        df = df.rename(columns={"date": "Date"})
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")
    elif df.index.name and df.index.name.lower() == "date":
        df.index = pd.to_datetime(df.index)
        df.index.name = "Date"
    else:
        df.index = pd.to_datetime(df.index)
        df.index.name = "Date"

    df = df.sort_index()
    # Cast numerics
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    return df


def load_from_csv(filepath: str) -> pd.DataFrame:
    """Load OHLCV data from a CSV file."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"CSV file not found: {filepath}")
    df = pd.read_csv(filepath)
    df = _normalize_columns(df)
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")
    return df


def load_from_yfinance(
    symbol: str,
    start: str,
    end: str,
    interval: str = "1d",
    log_fn: Optional[Callable] = None,
) -> pd.DataFrame:
    """
    Download OHLCV data from yfinance.

    Args:
        symbol: Ticker symbol e.g. 'AAPL'
        start: Start date 'YYYY-MM-DD'
        end: End date 'YYYY-MM-DD'
        interval: yfinance interval string
        log_fn: Optional callback(msg: str) for progress logging
    """
    try:
        import yfinance as yf
        try:
            yf_cache = importlib.import_module("yfinance.cache")
            yf_shared = importlib.import_module("yfinance.shared")
        except ImportError:
            yf_cache = getattr(yf, "cache", None)
            yf_shared = getattr(yf, "shared", None)
            if yf_cache is None or yf_shared is None:
                raise
    except ImportError:
        raise ImportError("yfinance not installed. Run: pip install yfinance")

    os.makedirs(YFINANCE_CACHE_DIR, exist_ok=True)
    yf_cache.set_cache_location(YFINANCE_CACHE_DIR)

    start, end = _cap_yfinance_intraday_range(start, end, interval, log_fn=log_fn)

    if log_fn:
        log_fn(f"[yfinance] Downloading {symbol} | {interval} | {start} → {end}")

    try:
        direct_df = _load_from_yahoo_chart_api(symbol, start, end, interval, log_fn=log_fn)
        if direct_df is not None and not direct_df.empty:
            if log_fn:
                log_fn(f"[yfinance] Received {len(direct_df)} bars for {symbol} via Yahoo chart API")
            return _normalize_columns(direct_df)
    except Exception as e:
        if log_fn:
            log_fn(f"[yfinance] Yahoo chart API request failed for {symbol}: {e}")

    def capture_shared_error():
        return (
            yf_shared._ERRORS.get(symbol) or
            yf_shared._ERRORS.get(symbol.upper()) or
            yf_shared._TRACEBACKS.get(symbol) or
            yf_shared._TRACEBACKS.get(symbol.upper()) or
            ""
        )

    def clear_yfinance_state():
        try:
            yf_cache.get_tz_cache().store(symbol, None)
            yf_cache.get_tz_cache().store(symbol.upper(), None)
        except Exception:
            pass
        try:
            yf_cache.get_cookie_cache().store("basic", None)
            yf_cache.get_cookie_cache().store("csrf", None)
        except Exception:
            pass
        yf_shared._ERRORS = {}
        yf_shared._TRACEBACKS = {}

    def fetch_once():
        df_local = pd.DataFrame()
        last_error_local = None
        yf_shared._ERRORS = {}
        yf_shared._TRACEBACKS = {}
        yf_logger = logging.getLogger("yfinance")
        previous_level = yf_logger.level
        previous_disabled = yf_logger.disabled
        yf_logger.disabled = True

        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                try:
                    ticker = yf.Ticker(symbol)
                    df_local = ticker.history(start=start, end=end, interval=interval, auto_adjust=True)
                except Exception as e:
                    last_error_local = e
                    if log_fn:
                        log_fn(f"[yfinance] ticker.history failed for {symbol}: {e}")

                shared_error = capture_shared_error()
                if shared_error and not last_error_local:
                    last_error_local = ValueError(shared_error)

                if df_local.empty:
                    try:
                        fallback_df = yf.download(
                            symbol,
                            start=start,
                            end=end,
                            interval=interval,
                            auto_adjust=True,
                            progress=False,
                            threads=False,
                        )
                        if fallback_df is not None and not fallback_df.empty:
                            df_local = fallback_df
                            if log_fn:
                                log_fn(f"[yfinance] Recovered {symbol} data via yf.download fallback")
                    except Exception as e:
                        last_error_local = e
                        if log_fn:
                            log_fn(f"[yfinance] yf.download fallback failed for {symbol}: {e}")

                shared_error = capture_shared_error()
                if shared_error:
                    last_error_local = ValueError(shared_error)
        finally:
            yf_logger.setLevel(previous_level)
            yf_logger.disabled = previous_disabled

        return df_local, last_error_local

    df, last_error = fetch_once()

    provider_issue = str(last_error or "")
    provider_issue_markers = [
        "Expecting value",
        "No timezone found",
        "possibly delisted",
        "HTTPSConnectionPool",
        "Failed to resolve",
        "JSONDecodeError",
        "YFTzMissingError",
    ]

    if df.empty and provider_issue and any(marker in provider_issue for marker in provider_issue_markers):
        if log_fn:
            log_fn(f"[yfinance] Clearing cached Yahoo state and retrying {symbol} once")
        clear_yfinance_state()
        retry_df, retry_error = fetch_once()
        if not retry_df.empty:
            df = retry_df
            last_error = None
        elif retry_error:
            last_error = retry_error

    if df.empty:
        provider_issue = str(last_error or "")
        if provider_issue and any(hint in provider_issue for hint in provider_issue_markers):
            raise ValueError(
                f"Yahoo Finance did not return usable data for {symbol}. "
                f"Provider response: {provider_issue}. "
                "This is usually a Yahoo/provider issue or stale cache, not necessarily an invalid symbol. "
                "Try again, use Broker source, or load a CSV."
            )
        if interval in ["1m", "2m", "5m", "15m", "30m", "90m"]:
            raise ValueError(
                f"No data returned for {symbol}. "
                f"Yahoo Finance limits intraday data ({interval}) to the last 60 days. "
                "Please adjust your start date or use a daily ('1d') interval."
            )
        elif interval in ["60m", "1h"]:
            raise ValueError(
                f"No data returned for {symbol}. "
                f"Yahoo Finance limits intraday data ({interval}) to the last 730 days. "
                "Please adjust your start date or use a daily ('1d') interval."
            )
        else:
            raise ValueError(
                f"No data returned for {symbol}. "
                "Check symbol, date range, and interval validity."
            )

    if log_fn:
        log_fn(f"[yfinance] Received {len(df)} bars for {symbol}")

    df = _normalize_columns(df)
    return df


def _cap_yfinance_intraday_range(
    start: str,
    end: str,
    interval: str,
    log_fn: Optional[Callable] = None,
) -> tuple[str, str]:
    """
    Clamp intraday requests to stay safely inside Yahoo Finance lookback limits.

    Yahoo's exact boundary can be unreliable for intraday intervals, so we keep
    a 1-day buffer for 60m/1h and sub-hour intervals.
    """
    max_days = YFINANCE_INTRADAY_LOOKBACK_DAYS.get(interval)
    if max_days is None:
        return start, end

    start_dt = pd.to_datetime(start, errors="coerce")
    end_dt = pd.to_datetime(end, errors="coerce")
    if pd.isna(start_dt) or pd.isna(end_dt):
        return start, end

    start_dt = start_dt.normalize()
    end_dt = end_dt.normalize()
    if start_dt >= end_dt:
        return start, end

    if (end_dt - start_dt).days <= max_days:
        return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")

    capped_start = end_dt - pd.Timedelta(days=max_days)
    if log_fn:
        log_fn(
            f"[yfinance] Adjusted {interval} start date from {start_dt.date()} "
            f"to {capped_start.date()} to stay within Yahoo Finance intraday limits"
        )
    return capped_start.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")


def load_from_broker(
    broker: str,
    symbol: str,
    start: str,
    end: str,
    interval: str = "1d",
    api_key: str = "",
    secret_key: str = "",
    log_fn: Optional[Callable] = None,
) -> pd.DataFrame:
    """
    Load data from a supported broker.
    Currently supports: alpaca, zerodha
    Falls back to yfinance if broker not configured.
    """
    if log_fn:
        log_fn(f"[broker:{broker}] Connecting to {broker.upper()} API...")

    if broker == "alpaca":
        from backend.modules.broker_connector import AlpacaConnector
        conn = AlpacaConnector(api_key=api_key, secret_key=secret_key)
        return conn.get_bars(symbol, start, end, interval, log_fn=log_fn)
    elif broker == "zerodha":
        from backend.modules.broker_connector import ZerodhaConnector
        conn = ZerodhaConnector(api_key=api_key, access_token=secret_key)
        # Zerodha expects 'day' interval default, but it's handled internally usually.
        # We pass it through format mapping internally
        return conn.get_historical(symbol, start, end, interval, log_fn=log_fn)
    elif broker == "fyers":
        from backend.modules.broker_connector import FyersConnector
        conn = FyersConnector(api_key=api_key, access_token=secret_key)
        return conn.get_historical(symbol, start, end, interval, log_fn=log_fn)
    else:
        if log_fn:
            log_fn(f"[broker] Unknown broker '{broker}', falling back to yfinance")
        return load_from_yfinance(symbol, start, end, interval, log_fn)


def resolve_period(period: str) -> tuple[str, str]:
    """Convert period string (1m, 3m, 6m, 1y, 2y, 3y, 5y) to start/end dates."""
    from dateutil.relativedelta import relativedelta
    end_dt = datetime.now()
    
    if period == "1m": delta = relativedelta(months=1)
    elif period == "3m": delta = relativedelta(months=3)
    elif period == "6m": delta = relativedelta(months=6)
    elif period == "1y": delta = relativedelta(years=1)
    elif period == "2y": delta = relativedelta(years=2)
    elif period == "3y": delta = relativedelta(years=3)
    elif period == "5y": delta = relativedelta(years=5)
    else: delta = relativedelta(years=1)
    
    start_dt = end_dt - delta
    return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample OHLCV data to a higher timeframe."""
    ohlcv_agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    return df.resample(rule).agg(ohlcv_agg).dropna()


def load_data(
    source: str,
    symbol: str,
    start: str,
    end: str,
    interval: str = "1d",
    csv_path: Optional[str] = None,
    broker: Optional[str] = None,
    api_key: str = "",
    secret_key: str = "",
    log_fn: Optional[Callable] = None,
) -> pd.DataFrame:
    """
    Unified data loading function.

    source: 'yfinance' | 'csv' | 'broker'
    """
    if source == "csv":
        if not csv_path:
            raise ValueError("csv_path must be provided when source='csv'")
        if log_fn:
            log_fn(f"[csv] Loading {os.path.basename(csv_path)}")
        df = load_from_csv(csv_path)
        # Filter by date range if provided
        if start and end:
            df = df.loc[start:end]
        if log_fn:
            log_fn(f"[csv] Loaded {len(df)} bars")
        return df
    elif source == "broker" and broker:
        return load_from_broker(broker, symbol, start, end, interval, api_key, secret_key, log_fn)
    else:
        return load_from_yfinance(symbol, start, end, interval, log_fn)
