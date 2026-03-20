"""
Comprehensive tests for all backend modules.
Run with: pytest backend/tests/ -v
"""

import os
import sys
import sqlite3
from types import SimpleNamespace
import pytest
import numpy as np
import pandas as pd

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.modules.data_ingestion import load_from_csv, load_from_yfinance, _normalize_columns, _cap_yfinance_intraday_range
from backend.modules.strategy_engine import ema_crossover, rsi_mean_reversion, breakout, macd, run_strategy
from backend.modules.backtest_engine import run_backtest, compute_position_size, kelly_fraction
from backend.modules.metrics_engine import (
    compute_cagr, compute_max_drawdown, compute_sharpe,
    compute_sortino, compute_trade_stats, compute_all_metrics
)
import backend.api.routes as api_routes
import backend.modules.history_manager as history_manager
import backend.modules.broker_connector as broker_connector


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def sample_df():
    """Generate a realistic OHLCV DataFrame for testing."""
    np.random.seed(42)
    n = 500
    dates = pd.date_range("2021-01-01", periods=n, freq="B")
    prices = 100.0 * np.exp(np.cumsum(np.random.normal(0.0003, 0.015, n)))
    df = pd.DataFrame({
        "open":   prices * (1 + np.random.uniform(-0.005, 0.005, n)),
        "high":   prices * (1 + np.random.uniform(0.001, 0.020, n)),
        "low":    prices * (1 - np.random.uniform(0.001, 0.020, n)),
        "close":  prices,
        "volume": np.random.randint(1_000_000, 10_000_000, n),
    }, index=dates)
    df.index.name = "Date"
    return df


@pytest.fixture
def sample_csv(tmp_path, sample_df):
    """Write sample_df to a temp CSV and return path."""
    path = str(tmp_path / "test_AAPL.csv")
    sample_df.to_csv(path)
    return path


@pytest.fixture
def equity_curve(sample_df):
    """A simple equity curve list."""
    values = [100_000 * (1 + 0.0003) ** i for i in range(len(sample_df))]
    return [{"date": str(d.date()), "value": v} for d, v in zip(sample_df.index, values)]


@pytest.fixture
def local_request():
    return SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))


@pytest.fixture
def remote_request():
    return SimpleNamespace(client=SimpleNamespace(host="10.10.10.10"))


# ─────────────────────────────────────────────────────────────
# Data Ingestion Tests
# ─────────────────────────────────────────────────────────────

class TestDataIngestion:

    def test_load_csv_success(self, sample_csv, sample_df):
        df = load_from_csv(sample_csv)
        assert len(df) == len(sample_df)
        assert {"open", "high", "low", "close", "volume"}.issubset(df.columns)
        assert df.index.name == "Date"

    def test_load_csv_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_from_csv("/nonexistent/path/data.csv")

    def test_normalize_columns(self, sample_df):
        df = sample_df.copy()
        df.columns = [c.upper() for c in df.columns]
        norm = _normalize_columns(df)
        assert "close" in norm.columns
        assert norm.index.name == "Date"

    def test_normalize_adj_close(self, sample_df):
        df = sample_df.copy()
        df["adj close"] = df["close"] * 0.99
        df = df.rename(columns={"close": "raw_close"})
        norm = _normalize_columns(df)
        # adj close should be renamed to close
        assert "close" in norm.columns

    def test_ohlcv_integrity_after_load(self, sample_csv):
        df = load_from_csv(sample_csv)
        assert (df["high"] >= df["low"]).all(), "High must be >= Low"
        assert df["volume"].min() >= 0, "Volume must be non-negative"
        assert df["close"].isna().sum() == 0, "No NaN in close"

    def test_yfinance_intraday_range_is_clamped_with_safety_buffer(self):
        start, end = _cap_yfinance_intraday_range("2024-03-19", "2026-03-19", "1h")
        assert start == "2024-03-20"
        assert end == "2026-03-19"

    def test_yfinance_daily_range_is_not_clamped(self):
        start, end = _cap_yfinance_intraday_range("2024-03-19", "2026-03-19", "1d")
        assert start == "2024-03-19"
        assert end == "2026-03-19"

    def test_yfinance_download_fallback_recovers_from_ticker_history_error(self, monkeypatch, sample_df):
        monkeypatch.setattr("backend.modules.data_ingestion._load_from_yahoo_chart_api", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("chart api failed")))

        class FakeTicker:
            def __init__(self, symbol):
                self.symbol = symbol

            def history(self, **kwargs):
                raise ValueError("Expecting value: line 1 column 1 (char 0)")

        def fake_download(*args, **kwargs):
            return sample_df.copy()

        class DummyStore:
            def store(self, *args, **kwargs):
                return None

        fake_cache = SimpleNamespace(
            set_cache_location=lambda *args, **kwargs: None,
            get_tz_cache=lambda: DummyStore(),
            get_cookie_cache=lambda: DummyStore(),
        )
        fake_shared = SimpleNamespace(_ERRORS={}, _TRACEBACKS={})
        fake_yfinance = SimpleNamespace(Ticker=FakeTicker, download=fake_download)
        fake_yfinance.cache = fake_cache
        fake_yfinance.shared = fake_shared
        monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)
        monkeypatch.setitem(sys.modules, "yfinance.cache", fake_cache)
        monkeypatch.setitem(sys.modules, "yfinance.shared", fake_shared)

        df = load_from_yfinance("BSE.NS", "2025-12-19", "2026-03-19", "1d")

        assert not df.empty
        assert {"open", "high", "low", "close", "volume"}.issubset(df.columns)


# ─────────────────────────────────────────────────────────────
# Strategy Engine Tests
# ─────────────────────────────────────────────────────────────

class TestStrategyEngine:

    def test_ema_crossover_output(self, sample_df):
        result = ema_crossover(sample_df, fast=5, slow=20)
        assert "ema_fast" in result.columns
        assert "ema_slow" in result.columns
        assert "signal" in result.columns
        assert set(result["signal"].unique()).issubset({-1, 0, 1})

    def test_ema_crossover_signal_count(self, sample_df):
        result = ema_crossover(sample_df, fast=5, slow=20)
        buys = (result["signal"] == 1).sum()
        sells = (result["signal"] == -1).sum()
        assert buys > 0, "Should have at least one buy signal"
        assert sells > 0, "Should have at least one sell signal"

    def test_ema_crossover_signals_only_fire_on_true_crosses(self, sample_df):
        result = ema_crossover(sample_df, fast=12, slow=26)
        prev_fast = result["ema_fast"].shift(1)
        prev_slow = result["ema_slow"].shift(1)

        buys = result[result["signal"] == 1]
        sells = result[result["signal"] == -1]

        assert ((prev_fast.loc[buys.index] <= prev_slow.loc[buys.index]) & (buys["ema_fast"] > buys["ema_slow"])).all()
        assert ((prev_fast.loc[sells.index] >= prev_slow.loc[sells.index]) & (sells["ema_fast"] < sells["ema_slow"])).all()

    def test_ema_intrabar_can_signal_before_close_confirmation(self):
        dates = pd.date_range("2021-01-01", periods=3, freq="D")
        df = pd.DataFrame({
            "open": [105.0, 103.0, 104.0],
            "high": [106.0, 104.0, 105.0],
            "low": [104.0, 102.0, 100.0],
            "close": [105.0, 103.0, 101.0],
            "volume": [1_000] * 3,
        }, index=dates)

        on_close = ema_crossover(df, fast=2, slow=4, execution_mode="on_close")
        intrabar = ema_crossover(df, fast=2, slow=4, execution_mode="intrabar")

        assert on_close.loc[dates[2], "signal"] == 0
        assert intrabar.loc[dates[2], "signal"] == 1
        assert intrabar.loc[dates[2], "entry_trigger_price"] == pytest.approx(104.8666667)
        assert intrabar.loc[dates[2], "close"] < intrabar.loc[dates[2], "entry_trigger_price"] < intrabar.loc[dates[2], "high"]

    def test_ema_intrabar_can_exit_before_close_confirmation(self):
        dates = pd.date_range("2021-01-01", periods=5, freq="D")
        df = pd.DataFrame({
            "open": [95.0, 97.0, 99.0, 101.0, 100.4],
            "high": [96.0, 98.0, 100.0, 102.0, 101.0],
            "low": [94.0, 96.0, 98.0, 100.0, 96.5],
            "close": [95.0, 97.0, 99.0, 101.0, 100.4],
            "volume": [1_000] * 5,
        }, index=dates)

        on_close = ema_crossover(df, fast=2, slow=4, execution_mode="on_close")
        intrabar = ema_crossover(df, fast=2, slow=4, execution_mode="intrabar")

        assert on_close.loc[dates[4], "signal"] == 0
        assert intrabar.loc[dates[4], "signal"] == -1
        assert intrabar.loc[dates[4], "exit_trigger_price"] == pytest.approx(96.9117037)
        assert intrabar.loc[dates[4], "low"] < intrabar.loc[dates[4], "exit_trigger_price"] < intrabar.loc[dates[4], "close"]

    def test_rsi_range(self, sample_df):
        result = rsi_mean_reversion(sample_df, period=14)
        rsi_valid = result["rsi"].dropna()
        assert (rsi_valid >= 0).all() and (rsi_valid <= 100).all(), "RSI must be 0-100"

    def test_rsi_handles_monotonic_rally_without_nan(self):
        dates = pd.date_range("2021-01-01", periods=20, freq="D")
        df = pd.DataFrame({
            "open": range(100, 120),
            "high": range(101, 121),
            "low": range(99, 119),
            "close": range(100, 120),
            "volume": [1_000] * 20,
        }, index=dates)

        result = rsi_mean_reversion(df, period=14, oversold=30, overbought=70)

        assert result["rsi"].iloc[-1] == 100.0
        assert (result["signal"] == -1).sum() >= 1

    def test_rsi_signals(self, sample_df):
        result = rsi_mean_reversion(sample_df, oversold=30, overbought=70)
        assert "signal" in result.columns
        assert set(result["signal"].unique()).issubset({-1, 0, 1})

    def test_rsi_signals_only_fire_on_threshold_crosses(self, sample_df):
        oversold = 30
        overbought = 70
        result = rsi_mean_reversion(sample_df, oversold=oversold, overbought=overbought)
        prev_rsi = result["rsi"].shift(1)

        buys = result[result["signal"] == 1]
        sells = result[result["signal"] == -1]

        assert ((buys["rsi"] < oversold) & (prev_rsi.loc[buys.index] >= oversold)).all()
        assert ((sells["rsi"] > overbought) & (prev_rsi.loc[sells.index] <= overbought)).all()

    def test_breakout_channels(self, sample_df):
        result = breakout(sample_df, window=20)
        assert "channel_high" in result.columns
        assert "channel_low" in result.columns
        valid_channels = result[["channel_high", "channel_low"]].dropna()
        assert (valid_channels["channel_high"] >= valid_channels["channel_low"]).all()

    def test_breakout_signals_when_level_is_hit_intrabar(self):
        dates = pd.date_range("2021-01-01", periods=3, freq="D")
        df = pd.DataFrame({
            "open": [100.0, 100.5, 100.4],
            "high": [101.0, 102.0, 102.5],
            "low": [99.0, 100.0, 100.1],
            "close": [100.5, 101.5, 100.8],
            "volume": [1_000, 1_000, 1_000],
        }, index=dates)

        result = breakout(df, window=2)

        assert result.loc[dates[2], "signal"] == 1
        assert result.loc[dates[2], "entry_trigger_price"] == 102.0
        assert result.loc[dates[2], "close"] < result.loc[dates[2], "entry_trigger_price"]

    def test_breakout_signals_only_fire_when_channel_is_breached(self, sample_df):
        result = breakout(sample_df, window=20)
        buys = result[result["signal"] == 1]
        sells = result[result["signal"] == -1]

        assert (buys["high"] >= buys["channel_high"]).all()
        assert (sells["low"] <= sells["channel_low"]).all()

    def test_breakout_ambiguous_bar_stays_flat_without_close_confirmation(self):
        dates = pd.date_range("2021-01-01", periods=4, freq="D")
        df = pd.DataFrame({
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [102.0, 102.0, 102.0, 103.0],
            "low": [98.0, 98.0, 98.0, 97.0],
            "close": [100.0, 100.0, 100.0, 100.0],
            "volume": [1_000, 1_000, 1_000, 1_000],
        }, index=dates)

        result = breakout(df, window=3)

        assert result.loc[dates[3], "signal"] == 0

    def test_macd_output(self, sample_df):
        result = macd(sample_df, fast=12, slow=26, signal_period=9)
        assert "macd_line" in result.columns
        assert "macd_signal" in result.columns
        assert "macd_hist" in result.columns

    def test_macd_signals_only_fire_on_true_crosses(self, sample_df):
        result = macd(sample_df, fast=12, slow=26, signal_period=9)
        prev_macd = result["macd_line"].shift(1)
        prev_signal = result["macd_signal"].shift(1)
        buys = result[result["signal"] == 1]
        sells = result[result["signal"] == -1]

        assert ((prev_macd.loc[buys.index] <= prev_signal.loc[buys.index]) & (buys["macd_line"] > buys["macd_signal"])).all()
        assert ((prev_macd.loc[sells.index] >= prev_signal.loc[sells.index]) & (sells["macd_line"] < sells["macd_signal"])).all()

    def test_macd_intrabar_can_signal_before_close_confirmation(self):
        dates = pd.date_range("2021-01-01", periods=6, freq="D")
        df = pd.DataFrame({
            "open": [100.0, 99.0, 98.0, 97.0, 96.0, 96.4],
            "high": [101.0, 100.0, 99.0, 98.0, 97.5, 98.5],
            "low": [99.0, 98.0, 97.0, 96.0, 95.0, 96.0],
            "close": [100.0, 99.0, 98.0, 97.0, 96.0, 96.4],
            "volume": [1_000] * 6,
        }, index=dates)

        on_close = macd(df, fast=3, slow=6, signal_period=3, execution_mode="on_close")
        intrabar = macd(df, fast=3, slow=6, signal_period=3, execution_mode="intrabar")

        assert on_close.loc[dates[5], "signal"] == 0
        assert intrabar.loc[dates[5], "signal"] == 1
        assert intrabar.loc[dates[5], "entry_trigger_price"] == pytest.approx(96.6770357)
        assert intrabar.loc[dates[5], "close"] < intrabar.loc[dates[5], "entry_trigger_price"] < intrabar.loc[dates[5], "high"]

    def test_macd_intrabar_can_exit_before_close_confirmation(self):
        dates = pd.date_range("2021-01-01", periods=6, freq="D")
        df = pd.DataFrame({
            "open": [96.0, 97.0, 98.0, 99.0, 100.0, 99.6],
            "high": [97.0, 98.0, 99.0, 100.0, 101.0, 100.0],
            "low": [95.0, 96.0, 97.0, 98.0, 99.0, 97.5],
            "close": [96.0, 97.0, 98.0, 99.0, 100.0, 99.6],
            "volume": [1_000] * 6,
        }, index=dates)

        on_close = macd(df, fast=3, slow=6, signal_period=3, execution_mode="on_close")
        intrabar = macd(df, fast=3, slow=6, signal_period=3, execution_mode="intrabar")

        assert on_close.loc[dates[5], "signal"] == 0
        assert intrabar.loc[dates[5], "signal"] == -1
        assert intrabar.loc[dates[5], "exit_trigger_price"] == pytest.approx(99.3229643)
        assert intrabar.loc[dates[5], "low"] < intrabar.loc[dates[5], "exit_trigger_price"] < intrabar.loc[dates[5], "close"]

    def test_run_strategy_dispatch(self, sample_df):
        for name in ["ema_crossover", "rsi_mean_reversion", "breakout", "macd"]:
            result = run_strategy(sample_df, name, {})
            assert "signal" in result.columns, f"{name} missing signal column"

    def test_run_strategy_dispatches_execution_mode(self):
        dates = pd.date_range("2021-01-01", periods=3, freq="D")
        df = pd.DataFrame({
            "open": [105.0, 103.0, 104.0],
            "high": [106.0, 104.0, 105.0],
            "low": [104.0, 102.0, 100.0],
            "close": [105.0, 103.0, 101.0],
            "volume": [1_000] * 3,
        }, index=dates)

        on_close = run_strategy(df, "ema_crossover", {"fast": 2, "slow": 4}, execution_mode="on_close")
        intrabar = run_strategy(df, "ema_crossover", {"fast": 2, "slow": 4}, execution_mode="intrabar")

        assert on_close.loc[dates[2], "signal"] == 0
        assert intrabar.loc[dates[2], "signal"] == 1

    def test_run_strategy_invalid(self, sample_df):
        with pytest.raises(ValueError):
            run_strategy(sample_df, "nonexistent_strategy", {})

    def test_strategy_no_nan_in_signal(self, sample_df):
        result = ema_crossover(sample_df)
        assert result["signal"].isna().sum() == 0


# ─────────────────────────────────────────────────────────────
# Backtest Engine Tests
# ─────────────────────────────────────────────────────────────

class TestBacktestEngine:

    def test_kelly_fraction_range(self):
        kf = kelly_fraction(0.6, 200, 100)
        assert 0 <= kf <= 0.25, "Kelly fraction should be capped at 0.25"

    def test_kelly_fraction_zero_loss(self):
        kf = kelly_fraction(0.6, 200, 0)
        assert kf == 0.0

    def test_position_size_fixed(self):
        shares = compute_position_size(100_000, 150, method="fixed", fixed_units=50)
        assert shares == 50

    def test_position_size_pct(self):
        shares = compute_position_size(100_000, 100, method="pct_capital", pct=10)
        assert shares == 100  # 10_000 / 100 = 100 shares

    def test_position_size_kelly(self):
        shares = compute_position_size(100_000, 100, method="kelly", win_rate=0.6, avg_win=200, avg_loss=100)
        assert shares >= 1

    def test_backtest_returns_structure(self, sample_df):
        df_s = ema_crossover(sample_df)
        result = run_backtest(df_s, initial_capital=100_000)
        assert "trades" in result
        assert "equity_curve" in result
        assert "initial_capital" in result
        assert "final_value" in result
        assert "total_trades" in result

    def test_equity_curve_length(self, sample_df):
        df_s = rsi_mean_reversion(sample_df)
        result = run_backtest(df_s)
        assert len(result["equity_curve"]) == len(sample_df)

    def test_equity_curve_starts_at_capital(self, sample_df):
        cap = 100_000
        df_s = ema_crossover(sample_df)
        result = run_backtest(df_s, initial_capital=cap)
        # First value should be ~initial_capital (before any trade)
        first_val = result["equity_curve"][0]["value"]
        assert abs(first_val - cap) < cap * 0.05

    def test_no_signal_no_trades(self, sample_df):
        df_no_signal = sample_df.copy()
        df_no_signal["signal"] = 0
        result = run_backtest(df_no_signal)
        assert result["total_trades"] == 0

    def test_capital_conservation(self, sample_df):
        """Final value should be positive and not absurdly large."""
        df_s = breakout(sample_df, window=20)
        result = run_backtest(df_s, initial_capital=100_000)
        assert result["final_value"] > 0
        assert result["final_value"] < 100_000 * 100  # sanity upper bound

    def test_missing_signal_column(self, sample_df):
        with pytest.raises(ValueError):
            run_backtest(sample_df)

    def test_trade_pnl_includes_both_entry_and_exit_commissions(self):
        dates = pd.date_range("2021-01-01", periods=2, freq="D")
        df = pd.DataFrame({
            "open": [100.0, 100.0],
            "high": [100.0, 100.0],
            "low": [100.0, 100.0],
            "close": [100.0, 100.0],
            "volume": [1_000, 1_000],
            "signal": [1, -1],
        }, index=dates)

        result = run_backtest(
            df,
            initial_capital=1_000,
            slippage_pct=0,
            commission=10,
            position_sizing="fixed",
            fixed_units=1,
        )

        assert result["trades"][0]["pnl"] == -20.0
        assert result["final_value"] == 980.0

    def test_forced_last_bar_close_does_not_double_count_holdings(self):
        dates = pd.date_range("2021-01-01", periods=2, freq="D")
        df = pd.DataFrame({
            "open": [100.0, 110.0],
            "high": [100.0, 110.0],
            "low": [100.0, 110.0],
            "close": [100.0, 110.0],
            "volume": [1_000, 1_000],
            "signal": [1, 0],
        }, index=dates)

        result = run_backtest(
            df,
            initial_capital=1_000,
            slippage_pct=0,
            commission=0,
            position_sizing="fixed",
            fixed_units=10,
        )

        assert result["trades"][0]["pnl"] == 100.0
        assert result["final_value"] == 1_100.0
        assert result["equity_curve"][-1]["value"] == result["final_value"]

    def test_intrabar_execution_uses_breakout_trigger_price(self):
        dates = pd.date_range("2021-01-01", periods=4, freq="D")
        df = pd.DataFrame({
            "open": [100.0, 100.5, 100.4, 100.6],
            "high": [101.0, 102.0, 102.5, 101.2],
            "low": [99.0, 100.0, 100.1, 99.0],
            "close": [100.5, 101.5, 100.8, 100.0],
            "volume": [1_000, 1_000, 1_000, 1_000],
        }, index=dates)
        signals = breakout(df, window=2)

        intrabar = run_backtest(
            signals,
            initial_capital=10_000,
            slippage_pct=0,
            commission=0,
            execution_mode="intrabar",
            position_sizing="fixed",
            fixed_units=1,
        )
        on_close = run_backtest(
            signals,
            initial_capital=10_000,
            slippage_pct=0,
            commission=0,
            execution_mode="on_close",
            position_sizing="fixed",
            fixed_units=1,
        )

        assert intrabar["trades"][0]["entry_price"] == 102.0
        assert on_close["trades"][0]["entry_price"] == 100.8

    def test_intrabar_breakout_exit_uses_channel_low(self):
        dates = pd.date_range("2021-01-01", periods=5, freq="D")
        df = pd.DataFrame({
            "open": [100.0, 100.0, 100.4, 100.0, 100.0],
            "high": [101.0, 102.0, 102.5, 100.5, 100.1],
            "low": [99.0, 100.0, 100.1, 98.5, 98.7],
            "close": [100.5, 101.5, 100.8, 99.5, 99.0],
            "volume": [1_000] * 5,
        }, index=dates)
        signals = breakout(df, window=2)

        intrabar = run_backtest(
            signals,
            initial_capital=10_000,
            slippage_pct=0,
            commission=0,
            execution_mode="intrabar",
            position_sizing="fixed",
            fixed_units=1,
        )

        assert intrabar["trades"][0]["exit_date"] == str(dates[3].date())
        assert intrabar["trades"][0]["exit_price"] == 100.0

    def test_ema_entries_and_exits_align_with_signal_dates_on_sample_csv(self):
        df = load_from_csv("backend/data/AAPL_sample.csv")
        signals = ema_crossover(df, fast=12, slow=26)
        bt = run_backtest(
            signals,
            initial_capital=100_000,
            slippage_pct=0,
            commission=0,
            execution_mode="on_close",
            position_sizing="fixed",
            fixed_units=1,
        )

        buy_dates = {str(idx.date()) for idx in signals.index[signals["signal"] == 1]}
        sell_dates = {str(idx.date()) for idx in signals.index[signals["signal"] == -1]}

        assert all(trade["entry_date"] in buy_dates for trade in bt["trades"])
        assert all(
            trade["type"] == "FORCED EXIT" or trade["exit_date"] in sell_dates
            for trade in bt["trades"]
        )

    def test_intrabar_execution_uses_ema_trigger_price(self):
        dates = pd.date_range("2021-01-01", periods=3, freq="D")
        df = pd.DataFrame({
            "open": [105.0, 103.0, 104.0],
            "high": [106.0, 104.0, 105.0],
            "low": [104.0, 102.0, 100.0],
            "close": [105.0, 103.0, 101.0],
            "volume": [1_000] * 3,
        }, index=dates)
        signals = ema_crossover(df, fast=2, slow=4, execution_mode="intrabar")

        intrabar = run_backtest(
            signals,
            initial_capital=10_000,
            slippage_pct=0,
            commission=0,
            execution_mode="intrabar",
            position_sizing="fixed",
            fixed_units=1,
        )

        assert intrabar["trades"][0]["entry_date"] == str(dates[2].date())
        assert intrabar["trades"][0]["entry_price"] == pytest.approx(104.8666667)

    def test_intrabar_execution_uses_macd_trigger_price(self):
        dates = pd.date_range("2021-01-01", periods=6, freq="D")
        df = pd.DataFrame({
            "open": [100.0, 99.0, 98.0, 97.0, 96.0, 96.4],
            "high": [101.0, 100.0, 99.0, 98.0, 97.5, 98.5],
            "low": [99.0, 98.0, 97.0, 96.0, 95.0, 96.0],
            "close": [100.0, 99.0, 98.0, 97.0, 96.0, 96.4],
            "volume": [1_000] * 6,
        }, index=dates)
        signals = macd(df, fast=3, slow=6, signal_period=3, execution_mode="intrabar")

        intrabar = run_backtest(
            signals,
            initial_capital=10_000,
            slippage_pct=0,
            commission=0,
            execution_mode="intrabar",
            position_sizing="fixed",
            fixed_units=1,
        )

        assert intrabar["trades"][0]["entry_date"] == str(dates[5].date())
        assert intrabar["trades"][0]["entry_price"] == pytest.approx(96.6770357)

    @pytest.mark.parametrize("strategy_name,params", [
        ("ema_crossover", {"fast": 12, "slow": 26}),
        ("rsi_mean_reversion", {"period": 14, "oversold": 30, "overbought": 70}),
        ("breakout", {"window": 20}),
        ("macd", {"fast": 12, "slow": 26, "signal_period": 9}),
    ])
    def test_strategy_trades_align_with_signal_dates_on_sample_csv(self, strategy_name, params):
        df = load_from_csv("backend/data/AAPL_sample.csv")
        signals = run_strategy(df, strategy_name, params)
        bt = run_backtest(
            signals,
            initial_capital=100_000,
            slippage_pct=0,
            commission=0,
            execution_mode="on_close",
            position_sizing="fixed",
            fixed_units=1,
        )

        buy_dates = {str(idx.date()) for idx in signals.index[signals["signal"] == 1]}
        sell_dates = {str(idx.date()) for idx in signals.index[signals["signal"] == -1]}

        assert all(trade["entry_date"] in buy_dates for trade in bt["trades"])
        assert all(
            trade["type"] == "FORCED EXIT" or trade["exit_date"] in sell_dates
            for trade in bt["trades"]
        )

    @pytest.mark.parametrize("strategy_name,params", [
        ("rsi_mean_reversion", {"period": 14, "oversold": 30, "overbought": 70}),
    ])
    def test_close_based_strategies_match_intrabar_execution(self, strategy_name, params):
        df = load_from_csv("backend/data/AAPL_sample.csv")
        signals = run_strategy(df, strategy_name, params)

        on_close = run_backtest(
            signals,
            initial_capital=100_000,
            slippage_pct=0,
            commission=0,
            execution_mode="on_close",
            position_sizing="fixed",
            fixed_units=1,
        )
        intrabar = run_backtest(
            signals,
            initial_capital=100_000,
            slippage_pct=0,
            commission=0,
            execution_mode="intrabar",
            position_sizing="fixed",
            fixed_units=1,
        )

        assert intrabar["trades"] == on_close["trades"]


# ─────────────────────────────────────────────────────────────
# Metrics Engine Tests
# ─────────────────────────────────────────────────────────────

class TestMetricsEngine:

    def test_cagr_positive_growth(self):
        cagr = compute_cagr(100_000, 200_000, 5)
        assert abs(cagr - (2 ** 0.2 - 1)) < 1e-6

    def test_cagr_no_growth(self):
        assert compute_cagr(100_000, 100_000, 5) == 0.0

    def test_cagr_zero_years(self):
        assert compute_cagr(100_000, 200_000, 0) == 0.0

    def test_max_drawdown_no_loss(self, equity_curve):
        dd = compute_max_drawdown(equity_curve)
        assert dd["max_drawdown_pct"] <= 0  # drawdown is non-positive

    def test_max_drawdown_known_value(self):
        curve = [{"date": f"2021-{i:02d}-01", "value": v} for i, v in enumerate([100, 110, 90, 95, 80, 120], 1)]
        dd = compute_max_drawdown(curve)
        # Peak=110, trough=80 → DD = (80-110)/110 ≈ -27.27%
        assert dd["max_drawdown_pct"] < -20

    def test_sharpe_positive_returns(self):
        returns = np.array([0.001] * 252)  # constant positive return
        sharpe = compute_sharpe(returns)
        assert sharpe > 0

    def test_sharpe_zero_std(self):
        returns = np.zeros(252)
        sharpe = compute_sharpe(returns)
        assert sharpe == 0.0

    def test_sortino_ratio(self):
        returns = np.random.normal(0.001, 0.01, 252)
        sortino = compute_sortino(returns)
        assert isinstance(sortino, float)

    def test_trade_stats_all_wins(self):
        trades = [{"pnl": 100, "pnl_pct": 2.0}, {"pnl": 200, "pnl_pct": 3.0}]
        stats = compute_trade_stats(trades)
        assert stats["win_rate"] == 100.0
        assert stats["losing_trades"] == 0

    def test_trade_stats_mixed(self):
        trades = [
            {"pnl": 100, "pnl_pct": 2.0},
            {"pnl": -50, "pnl_pct": -1.0},
            {"pnl": 200, "pnl_pct": 4.0},
            {"pnl": -30, "pnl_pct": -0.6},
        ]
        stats = compute_trade_stats(trades)
        assert stats["win_rate"] == 50.0
        assert stats["total_trades"] == 4
        assert stats["total_pnl"] == 220.0

    def test_trade_stats_empty(self):
        stats = compute_trade_stats([])
        assert stats["total_trades"] == 0
        assert stats["win_rate"] == 0.0

    def test_compute_all_metrics_integration(self, sample_df):
        df_s = ema_crossover(sample_df)
        bt = run_backtest(df_s, initial_capital=100_000)
        metrics = compute_all_metrics(
            equity_curve=bt["equity_curve"],
            trades=bt["trades"],
            initial_capital=100_000,
            final_value=bt["final_value"],
        )
        required = [
            "total_return_pct", "cagr_pct", "max_drawdown_pct",
            "sharpe_ratio", "sortino_ratio", "calmar_ratio",
            "win_rate", "expectancy", "profit_factor", "total_trades"
        ]
        for key in required:
            assert key in metrics, f"Missing metric: {key}"

    def test_metrics_types(self, sample_df):
        df_s = rsi_mean_reversion(sample_df)
        bt = run_backtest(df_s, initial_capital=100_000)
        metrics = compute_all_metrics(
            equity_curve=bt["equity_curve"],
            trades=bt["trades"],
            initial_capital=100_000,
            final_value=bt["final_value"],
        )
        assert isinstance(metrics["sharpe_ratio"], float)
        assert isinstance(metrics["cagr_pct"], float)
        assert isinstance(metrics["max_drawdown_pct"], float)


# ─────────────────────────────────────────────────────────────
# End-to-End Integration Test
# ─────────────────────────────────────────────────────────────

class TestEndToEnd:

    @pytest.mark.parametrize("strategy,params", [
        ("ema_crossover", {"fast": 10, "slow": 30}),
        ("rsi_mean_reversion", {"period": 14, "oversold": 30, "overbought": 70}),
        ("breakout", {"window": 20}),
        ("macd", {"fast": 12, "slow": 26, "signal_period": 9}),
    ])
    def test_full_pipeline(self, sample_df, strategy, params):
        df_s = run_strategy(sample_df, strategy, params)
        bt = run_backtest(df_s, initial_capital=100_000)
        metrics = compute_all_metrics(
            equity_curve=bt["equity_curve"],
            trades=bt["trades"],
            initial_capital=100_000,
            final_value=bt["final_value"],
        )
        assert metrics["total_trades"] == bt["total_trades"]
        assert len(bt["equity_curve"]) == len(sample_df)
        assert bt["final_value"] > 0


class TestApiRoutes:

    def test_resolve_broker_credentials_uses_env_defaults(self, monkeypatch):
        monkeypatch.setattr(api_routes, "_reload_runtime_config", lambda: None)
        monkeypatch.setattr(api_routes.config, "FYERS_APP_ID", "FY-APP")
        monkeypatch.setattr(api_routes.config, "FYERS_ACCESS_TOKEN", "ENV-FY-TOKEN")
        monkeypatch.setattr(api_routes.config, "ALPACA_API_KEY", "ALPACA-KEY")
        monkeypatch.setattr(api_routes.config, "ALPACA_SECRET_KEY", "ALPACA-SECRET")
        monkeypatch.setattr(api_routes.config, "ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

        assert api_routes._resolve_broker_credentials("fyers", "", "token", "") == ("FY-APP", "token", "")
        assert api_routes._resolve_broker_credentials("fyers", "", "", "") == ("FY-APP", "ENV-FY-TOKEN", "")
        assert api_routes._resolve_broker_credentials("alpaca", "", "", "") == (
            "ALPACA-KEY",
            "ALPACA-SECRET",
            "https://paper-api.alpaca.markets",
        )

    def test_broker_defaults_reports_fyers_env_status(self, monkeypatch, local_request):
        monkeypatch.setattr(api_routes, "_reload_runtime_config", lambda: None)
        monkeypatch.setattr(api_routes.config, "FYERS_APP_ID", "APP-123")
        monkeypatch.setattr(api_routes.config, "FYERS_SECRET_KEY", "SECRET-123")
        monkeypatch.setattr(api_routes.config, "FYERS_ACCESS_TOKEN", "TOKEN-123")
        monkeypatch.setattr(api_routes.config, "FYERS_REDIRECT_URI", "http://localhost:5173/broker/fyers/callback")

        defaults = api_routes.get_broker_defaults(local_request)

        assert defaults["fyers"]["has_api_key"] is True
        assert defaults["fyers"]["has_secret_key"] is True
        assert defaults["fyers"]["has_access_token"] is True
        assert defaults["fyers"]["auth_ready"] is True
        assert defaults["fyers"]["redirect_uri_absolute"] is True
        assert defaults["fyers"]["redirect_uri_valid"] is True
        assert defaults["fyers"]["redirect_uri"] == "http://localhost:5173/broker/fyers/callback"

    def test_fyers_login_url_uses_env_defaults(self, monkeypatch, local_request):
        monkeypatch.setattr(api_routes, "_reload_runtime_config", lambda: None)
        monkeypatch.setattr(api_routes.config, "FYERS_APP_ID", "APP-123")
        monkeypatch.setattr(api_routes.config, "FYERS_SECRET_KEY", "SECRET-123")
        monkeypatch.setattr(api_routes.config, "FYERS_REDIRECT_URI", "http://localhost:5173/broker/fyers/callback")

        captured = {}
        monkeypatch.setattr(
            api_routes,
            "generate_fyers_auth_url",
            lambda api_key, app_secret, redirect_uri, state: captured.update({
                "api_key": api_key,
                "app_secret": app_secret,
                "redirect_uri": redirect_uri,
                "state": state,
            }) or "https://fyers.example/login",
        )

        res = api_routes.create_fyers_login_url(api_routes.FyersLoginUrlRequest(), local_request)

        assert res["auth_url"] == "https://fyers.example/login"
        assert captured["api_key"] == "APP-123"
        assert captured["app_secret"] == "SECRET-123"
        assert captured["redirect_uri"] == "http://localhost:5173/broker/fyers/callback"
        assert captured["state"].startswith("quantforge-")

    def test_fyers_exchange_token_uses_env_defaults(self, monkeypatch, local_request):
        monkeypatch.setattr(api_routes, "_reload_runtime_config", lambda: None)
        monkeypatch.setattr(api_routes.config, "FYERS_APP_ID", "APP-123")
        monkeypatch.setattr(api_routes.config, "FYERS_SECRET_KEY", "SECRET-123")
        monkeypatch.setattr(api_routes.config, "FYERS_REDIRECT_URI", "http://localhost:5173/broker/fyers/callback")

        captured = {}
        monkeypatch.setattr(
            api_routes,
            "exchange_fyers_auth_code",
            lambda api_key, app_secret, redirect_uri, auth_code: captured.update({
                "api_key": api_key,
                "app_secret": app_secret,
                "redirect_uri": redirect_uri,
                "auth_code": auth_code,
            }) or {"status": "ok", "access_token": "TOKEN"},
        )

        res = api_routes.fyers_exchange_token(api_routes.FyersTokenExchangeRequest(auth_code="AUTH-CODE"), local_request)

        assert res["access_token"] == "TOKEN"
        assert captured == {
            "api_key": "APP-123",
            "app_secret": "SECRET-123",
            "redirect_uri": "http://localhost:5173/broker/fyers/callback",
            "auth_code": "AUTH-CODE",
        }

    def test_save_fyers_session_persists_env_and_runtime_config(self, monkeypatch, tmp_path, local_request):
        env_path = tmp_path / ".env"
        env_path.write_text("HOST=0.0.0.0\n", encoding="utf-8")

        monkeypatch.setattr(api_routes.config, "ENV_FILE", str(env_path))
        monkeypatch.setattr(api_routes.config, "FYERS_APP_ID", "")
        monkeypatch.setattr(api_routes.config, "FYERS_SECRET_KEY", "")
        monkeypatch.setattr(api_routes.config, "FYERS_REDIRECT_URI", "")
        monkeypatch.setattr(api_routes.config, "FYERS_ACCESS_TOKEN", "")

        res = api_routes.save_fyers_session(api_routes.FyersSaveSessionRequest(
            api_key="APP-123",
            app_secret="SECRET-123",
            redirect_uri="http://localhost:5173/broker/fyers/callback",
            access_token="TOKEN-123",
        ), local_request)

        env_text = env_path.read_text(encoding="utf-8")
        assert res["saved"] is True
        assert "FYERS_APP_ID=APP-123" in env_text
        assert "FYERS_SECRET_KEY=SECRET-123" in env_text
        assert "FYERS_REDIRECT_URI=http://localhost:5173/broker/fyers/callback" in env_text
        assert "FYERS_ACCESS_TOKEN=TOKEN-123" in env_text
        assert api_routes.config.FYERS_APP_ID == "APP-123"
        assert api_routes.config.FYERS_SECRET_KEY == "SECRET-123"
        assert api_routes.config.FYERS_REDIRECT_URI == "http://localhost:5173/broker/fyers/callback"
        assert api_routes.config.FYERS_ACCESS_TOKEN == "TOKEN-123"

    def test_save_fyers_session_allows_manual_mode_redirect_uri(self, monkeypatch, tmp_path, local_request):
        env_path = tmp_path / ".env"
        env_path.write_text("", encoding="utf-8")

        monkeypatch.setattr(api_routes.config, "ENV_FILE", str(env_path))
        monkeypatch.setattr(api_routes.config, "FYERS_APP_ID", "")
        monkeypatch.setattr(api_routes.config, "FYERS_SECRET_KEY", "")
        monkeypatch.setattr(api_routes.config, "FYERS_REDIRECT_URI", "")
        monkeypatch.setattr(api_routes.config, "FYERS_ACCESS_TOKEN", "")

        res = api_routes.save_fyers_session(api_routes.FyersSaveSessionRequest(
            api_key="APP-123",
            app_secret="SECRET-123",
            redirect_uri="https://www.google.com",
            access_token="TOKEN-123",
        ), local_request)

        env_text = env_path.read_text(encoding="utf-8")
        assert res["saved"] is True
        assert res["callback_ready"] is False
        assert "FYERS_REDIRECT_URI=https://www.google.com" in env_text

    def test_save_fyers_session_strips_app_id_prefix_from_access_token(self, monkeypatch, tmp_path, local_request):
        env_path = tmp_path / ".env"
        env_path.write_text("", encoding="utf-8")

        monkeypatch.setattr(api_routes.config, "ENV_FILE", str(env_path))
        monkeypatch.setattr(api_routes.config, "FYERS_APP_ID", "")
        monkeypatch.setattr(api_routes.config, "FYERS_SECRET_KEY", "")
        monkeypatch.setattr(api_routes.config, "FYERS_REDIRECT_URI", "")
        monkeypatch.setattr(api_routes.config, "FYERS_ACCESS_TOKEN", "")

        res = api_routes.save_fyers_session(api_routes.FyersSaveSessionRequest(
            api_key="APP-123",
            app_secret="SECRET-123",
            redirect_uri="https://www.google.com",
            access_token="APP-123:RAW-TOKEN-123",
        ), local_request)

        env_text = env_path.read_text(encoding="utf-8")
        assert res["saved"] is True
        assert "FYERS_ACCESS_TOKEN=RAW-TOKEN-123" in env_text
        assert api_routes.config.FYERS_ACCESS_TOKEN == "RAW-TOKEN-123"

    def test_fyers_login_url_allows_manual_mode_redirect_uri(self, monkeypatch, local_request):
        monkeypatch.setattr(api_routes, "_reload_runtime_config", lambda: None)
        monkeypatch.setattr(api_routes.config, "FYERS_APP_ID", "APP-123")
        monkeypatch.setattr(api_routes.config, "FYERS_SECRET_KEY", "SECRET-123")
        monkeypatch.setattr(api_routes.config, "FYERS_REDIRECT_URI", "https://www.google.com")

        captured = {}
        monkeypatch.setattr(
            api_routes,
            "generate_fyers_auth_url",
            lambda api_key, app_secret, redirect_uri, state: captured.update({
                "api_key": api_key,
                "app_secret": app_secret,
                "redirect_uri": redirect_uri,
                "state": state,
            }) or "https://fyers.example/login-manual",
        )

        res = api_routes.create_fyers_login_url(api_routes.FyersLoginUrlRequest(), local_request)

        assert res["auth_url"] == "https://fyers.example/login-manual"
        assert captured["redirect_uri"] == "https://www.google.com"
        assert captured["state"].startswith("quantforge-")

    def test_broker_defaults_reload_env_file_without_restart(self, monkeypatch, tmp_path, local_request):
        env_path = tmp_path / ".env"
        env_path.write_text(
            "FYERS_APP_ID=APP-123\n"
            "FYERS_SECRET_KEY=SECRET-123\n"
            "FYERS_REDIRECT_URI=https://www.google.com\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(api_routes.config, "ENV_FILE", str(env_path))
        monkeypatch.setattr(api_routes.config, "FYERS_REDIRECT_URI", "http://localhost:5173/broker/fyers/callback")

        defaults = api_routes.get_broker_defaults(local_request)

        assert defaults["fyers"]["redirect_uri"] == "https://www.google.com"
        assert defaults["fyers"]["redirect_uri_valid"] is False
        assert defaults["fyers"]["redirect_uri_absolute"] is True
        assert defaults["fyers"]["auth_ready"] is True

    def test_remote_request_cannot_read_broker_defaults(self, remote_request):
        with pytest.raises(Exception) as exc:
            api_routes.get_broker_defaults(remote_request)
        assert getattr(exc.value, "status_code", None) == 403

    def test_remote_request_cannot_save_fyers_session(self, remote_request):
        with pytest.raises(Exception) as exc:
            api_routes.save_fyers_session(
                api_routes.FyersSaveSessionRequest(
                    api_key="APP-123",
                    app_secret="SECRET-123",
                    redirect_uri="https://www.google.com",
                    access_token="TOKEN-123",
                ),
                remote_request,
            )
        assert getattr(exc.value, "status_code", None) == 403


class TestBrokerConnector:

    def test_normalize_fyers_access_token_accepts_prefixed_tokens(self):
        assert broker_connector.normalize_fyers_access_token("APP-123", "APP-123:RAW-TOKEN-123") == "RAW-TOKEN-123"
        assert broker_connector.normalize_fyers_access_token("APP-123", "RAW-TOKEN-123") == "RAW-TOKEN-123"
        assert broker_connector.normalize_fyers_access_token("APP-123", "Bearer RAW-TOKEN-123") == "RAW-TOKEN-123"

    def test_backtest_results_include_trade_log(self, monkeypatch, sample_df):
        df = sample_df.iloc[:3].copy()
        df["signal"] = [0, 1, -1]

        task_id = "unit-test-task"
        api_routes._tasks[task_id] = {
            "status": "running",
            "logs": [],
            "progress": 0,
            "results": None,
            "error": None,
        }

        monkeypatch.setattr(api_routes, "load_data", lambda **kwargs: df.copy())
        monkeypatch.setattr(
            api_routes,
            "run_strategy",
            lambda data, strategy_name, params, execution_mode="on_close", log_fn=None: df.copy(),
        )
        monkeypatch.setattr(api_routes, "save_backtest", lambda task_id, results: None)

        req = api_routes.BacktestRequest(
            symbol="AAPL",
            source="csv",
            csv_path="/tmp/ignored.csv",
            strategy="ema_crossover",
            initial_capital=10_000,
            slippage_pct=0,
            commission=0,
            position_sizing="fixed",
            fixed_units=1,
        )

        api_routes._run_backtest_task(task_id, req)

        results = api_routes._tasks[task_id]["results"]
        assert api_routes._tasks[task_id]["status"] == "complete"
        assert "trades" in results
        assert len(results["trades"]) == 1

    def test_history_details_endpoint_returns_saved_result(self, monkeypatch):
        payload = {"symbol": "AAPL", "strategy": "ema_crossover", "metrics": {}, "trades": []}
        monkeypatch.setattr(api_routes, "get_backtest_details", lambda task_id: payload if task_id == "abc" else None)

        assert api_routes.history_details("abc") == {"result": payload}
        with pytest.raises(api_routes.HTTPException):
            api_routes.history_details("missing")


class TestHistoryManager:

    def test_save_and_load_full_history_payload(self, tmp_path):
        original_db_path = history_manager.DB_PATH
        history_manager.DB_PATH = str(tmp_path / "history.db")
        try:
            history_manager.init_db()
            result = {
                "symbol": "AAPL",
                "strategy": "ema_crossover",
                "strategy_params": {"fast": 10, "slow": 30},
                "interval": "1d",
                "start": "2021-01-01",
                "end": "2021-12-31",
                "metrics": {"total_return_pct": 12.5, "total_trades": 4},
                "equity_curve": [{"date": "2021-01-01", "value": 100000.0}],
                "drawdown_series": [{"date": "2021-01-01", "drawdown": 0.0}],
                "indicator_data": {"ema_fast": [{"date": "2021-01-01", "value": 100.0}]},
                "trades": [{"entry_date": "2021-01-01", "exit_date": "2021-01-02", "pnl": 100.0, "pnl_pct": 1.0}],
                "total_bars": 252,
                "execution_mode": "on_close",
            }

            history_manager.save_backtest("bt-1", result)
            details = history_manager.get_backtest_details("bt-1")

            assert details["symbol"] == "AAPL"
            assert details["strategy_params"] == {"fast": 10, "slow": 30}
            assert details["equity_curve"] == result["equity_curve"]
            assert details["drawdown_series"] == result["drawdown_series"]
            assert details["history_summary_only"] is False
        finally:
            history_manager.DB_PATH = original_db_path

    def test_legacy_history_rows_still_load(self, tmp_path):
        original_db_path = history_manager.DB_PATH
        history_manager.DB_PATH = str(tmp_path / "legacy_history.db")
        try:
            conn = sqlite3.connect(history_manager.DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE backtests (
                    id TEXT PRIMARY KEY,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    symbol TEXT,
                    strategy TEXT,
                    interval TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    parameters TEXT,
                    metrics TEXT,
                    trades TEXT
                )
            """)
            cursor.execute("""
                INSERT INTO backtests (id, symbol, strategy, interval, start_date, end_date, parameters, metrics, trades)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "legacy-1",
                "MSFT",
                "macd",
                "1d",
                "2022-01-01",
                "2022-12-31",
                '{"fast": 12, "slow": 26}',
                '{"total_return_pct": 8.4, "total_trades": 2}',
                '[{"entry_date": "2022-01-01", "exit_date": "2022-01-10", "pnl": 42.0, "pnl_pct": 0.42}]',
            ))
            conn.commit()
            conn.close()

            history_manager.init_db()
            details = history_manager.get_backtest_details("legacy-1")

            assert details["symbol"] == "MSFT"
            assert details["strategy_params"] == {"fast": 12, "slow": 26}
            assert details["trades"][0]["pnl"] == 42.0
            assert details["equity_curve"] == []
            assert details["history_summary_only"] is True
        finally:
            history_manager.DB_PATH = original_db_path
