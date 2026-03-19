"""
strategy_engine.py
Generates buy/sell signals for EMA Crossover, RSI Mean Reversion, and Breakout strategies.
Returns a DataFrame with a 'signal' column: 1=buy, -1=sell, 0=hold.
"""

import pandas as pd
import numpy as np
from typing import Optional, Callable, Dict, Any


def _compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    zero_gain = avg_gain == 0
    zero_loss = avg_loss == 0
    rsi = rsi.mask(zero_loss & ~zero_gain, 100.0)
    rsi = rsi.mask(zero_gain & ~zero_loss, 0.0)
    rsi = rsi.mask(zero_gain & zero_loss, 50.0)
    return rsi


def _ema_alpha(period: int) -> float:
    return 2.0 / (period + 1.0)


def _touches_level(df: pd.DataFrame, level: pd.Series) -> pd.Series:
    return level.notna() & (df["low"] <= level) & (df["high"] >= level)


def _build_intrabar_cross_signal(
    previous_diff: pd.Series,
    current_diff: pd.Series,
    touches_trigger: pd.Series,
) -> pd.Series:
    """
    Approximate a live crossover from OHLC bars.

    If the trigger price is touched intrabar, we assume the first crossing follows
    the previous-bar state. When the previous bar ended exactly on the boundary,
    use the close-based state as a tiebreaker.
    """
    signal = pd.Series(0, index=previous_diff.index, dtype=int)
    prev_sign = np.sign(previous_diff.fillna(0.0))
    current_sign = np.sign(current_diff.fillna(0.0))

    bullish = touches_trigger & ((prev_sign < 0) | ((prev_sign == 0) & (current_sign > 0)))
    bearish = touches_trigger & ((prev_sign > 0) | ((prev_sign == 0) & (current_sign < 0)))

    signal.loc[bullish] = 1
    signal.loc[bearish] = -1
    return signal


def _ema_cross_price(
    prev_fast: pd.Series,
    prev_slow: pd.Series,
    fast: int,
    slow: int,
) -> pd.Series:
    alpha_fast = _ema_alpha(fast)
    alpha_slow = _ema_alpha(slow)
    denom = alpha_fast - alpha_slow
    if np.isclose(denom, 0.0):
        return pd.Series(np.nan, index=prev_fast.index, dtype=float)

    return (
        ((1.0 - alpha_slow) * prev_slow) - ((1.0 - alpha_fast) * prev_fast)
    ) / denom


def _macd_cross_price(
    prev_ema_fast: pd.Series,
    prev_ema_slow: pd.Series,
    prev_signal: pd.Series,
    fast: int,
    slow: int,
) -> pd.Series:
    alpha_fast = _ema_alpha(fast)
    alpha_slow = _ema_alpha(slow)
    denom = alpha_fast - alpha_slow
    if np.isclose(denom, 0.0):
        return pd.Series(np.nan, index=prev_ema_fast.index, dtype=float)

    intercept = ((1.0 - alpha_fast) * prev_ema_fast) - ((1.0 - alpha_slow) * prev_ema_slow)
    return (prev_signal - intercept) / denom


def ema_crossover(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    execution_mode: str = "on_close",
    log_fn: Optional[Callable] = None,
) -> pd.DataFrame:
    """
    EMA Crossover strategy.
    Buy when fast EMA crosses above slow EMA.
    Sell when fast EMA crosses below slow EMA.
    """
    if log_fn:
        log_fn(f"[strategy] Computing EMA({fast}) and EMA({slow})")

    out = df.copy()
    out["ema_fast"] = out["close"].ewm(span=fast, adjust=False).mean()
    out["ema_slow"] = out["close"].ewm(span=slow, adjust=False).mean()

    prev_fast = out["ema_fast"].shift(1)
    prev_slow = out["ema_slow"].shift(1)
    current_diff = out["ema_fast"] - out["ema_slow"]
    previous_diff = prev_fast - prev_slow
    trigger_price = _ema_cross_price(prev_fast, prev_slow, fast, slow)

    out["signal"] = 0
    out["entry_trigger_price"] = np.nan
    out["exit_trigger_price"] = np.nan

    if execution_mode == "intrabar":
        touches_trigger = _touches_level(out, trigger_price)
        out["signal"] = _build_intrabar_cross_signal(previous_diff, current_diff, touches_trigger)
        out.loc[out["signal"] == 1, "entry_trigger_price"] = trigger_price
        out.loc[out["signal"] == -1, "exit_trigger_price"] = trigger_price
        out["signal_price"] = np.where(
            out["signal"] == 1,
            out["entry_trigger_price"],
            np.where(out["signal"] == -1, out["exit_trigger_price"], np.nan),
        )
    else:
        out["_above"] = (current_diff > 0).astype(int)
        out["_prev_above"] = out["_above"].shift(1)
        out.loc[(out["_above"] == 1) & (out["_prev_above"] == 0), "signal"] = 1
        out.loc[(out["_above"] == 0) & (out["_prev_above"] == 1), "signal"] = -1
        out["signal_price"] = out["close"].where(out["signal"] != 0)
        out = out.drop(columns=["_above", "_prev_above"])

    out["position"] = np.where(current_diff > 0, 1, -1)

    if log_fn:
        buys = (out["signal"] == 1).sum()
        sells = (out["signal"] == -1).sum()
        log_fn(f"[strategy] EMA Crossover → {buys} buy signals, {sells} sell signals")

    return out


def rsi_mean_reversion(
    df: pd.DataFrame,
    period: int = 14,
    oversold: float = 30.0,
    overbought: float = 70.0,
    execution_mode: str = "on_close",
    log_fn: Optional[Callable] = None,
) -> pd.DataFrame:
    """
    RSI Mean Reversion strategy.
    Buy when RSI crosses below oversold threshold.
    Sell when RSI crosses above overbought threshold.
    """
    if log_fn:
        log_fn(f"[strategy] Computing RSI({period}) | oversold={oversold}, overbought={overbought}")

    out = df.copy()
    out["rsi"] = _compute_rsi(out["close"], period)

    out["_oversold"] = out["rsi"] < oversold
    out["_overbought"] = out["rsi"] > overbought
    out["_prev_oversold"] = out["_oversold"].shift(1, fill_value=False)
    out["_prev_overbought"] = out["_overbought"].shift(1, fill_value=False)

    out["signal"] = 0
    # Buy when RSI crosses into oversold zone
    out.loc[out["_oversold"] & ~out["_prev_oversold"], "signal"] = 1
    # Sell when RSI crosses into overbought zone
    out.loc[out["_overbought"] & ~out["_prev_overbought"], "signal"] = -1
    out["signal_price"] = out["close"].where(out["signal"] != 0)

    out = out.drop(columns=["_oversold", "_overbought", "_prev_oversold", "_prev_overbought"])

    if log_fn:
        buys = (out["signal"] == 1).sum()
        sells = (out["signal"] == -1).sum()
        log_fn(f"[strategy] RSI → {buys} buy signals, {sells} sell signals")

    return out


def breakout(
    df: pd.DataFrame,
    window: int = 20,
    execution_mode: str = "on_close",
    log_fn: Optional[Callable] = None,
) -> pd.DataFrame:
    """
    N-Day Breakout strategy (Donchian Channel).
    Buy when price hits the prior N-bar rolling high.
    Sell when price hits the prior N-bar rolling low.
    """
    if log_fn:
        log_fn(f"[strategy] Computing {window}-day Donchian Channel breakout")

    out = df.copy()
    out["channel_high"] = out["high"].rolling(window).max().shift(1)
    out["channel_low"] = out["low"].rolling(window).min().shift(1)

    above_trigger = out["channel_high"].notna() & (out["high"] >= out["channel_high"])
    below_trigger = out["channel_low"].notna() & (out["low"] <= out["channel_low"])
    both_triggered = above_trigger & below_trigger

    out["signal"] = 0
    out.loc[above_trigger & ~below_trigger, "signal"] = 1
    out.loc[below_trigger & ~above_trigger, "signal"] = -1

    # If both boundaries were hit in the same bar, only keep the direction that
    # also held through the close; otherwise leave the bar ambiguous with no signal.
    out.loc[both_triggered & (out["close"] >= out["channel_high"]), "signal"] = 1
    out.loc[both_triggered & (out["close"] <= out["channel_low"]), "signal"] = -1

    out["entry_trigger_price"] = out["channel_high"].where(out["signal"] == 1)
    out["exit_trigger_price"] = out["channel_low"].where(out["signal"] == -1)
    out["signal_price"] = np.where(
        out["signal"] == 1,
        out["entry_trigger_price"],
        np.where(out["signal"] == -1, out["exit_trigger_price"], np.nan),
    )

    if log_fn:
        buys = (out["signal"] == 1).sum()
        sells = (out["signal"] == -1).sum()
        log_fn(f"[strategy] Breakout → {buys} buy signals, {sells} sell signals")

    return out


def macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
    execution_mode: str = "on_close",
    log_fn: Optional[Callable] = None,
) -> pd.DataFrame:
    """
    MACD strategy.
    Buy when MACD line crosses above signal line.
    Sell when MACD line crosses below signal line.
    """
    if log_fn:
        log_fn(f"[strategy] Computing MACD({fast},{slow},{signal_period})")

    out = df.copy()
    out["ema_fast"] = out["close"].ewm(span=fast, adjust=False).mean()
    out["ema_slow"] = out["close"].ewm(span=slow, adjust=False).mean()
    out["macd_line"] = out["ema_fast"] - out["ema_slow"]
    out["macd_signal"] = out["macd_line"].ewm(span=signal_period, adjust=False).mean()
    out["macd_hist"] = out["macd_line"] - out["macd_signal"]

    out["signal"] = 0
    out["entry_trigger_price"] = np.nan
    out["exit_trigger_price"] = np.nan

    prev_macd = out["macd_line"].shift(1)
    prev_signal = out["macd_signal"].shift(1)
    current_diff = out["macd_line"] - out["macd_signal"]
    previous_diff = prev_macd - prev_signal

    if execution_mode == "intrabar":
        trigger_price = _macd_cross_price(
            prev_ema_fast=out["ema_fast"].shift(1),
            prev_ema_slow=out["ema_slow"].shift(1),
            prev_signal=prev_signal,
            fast=fast,
            slow=slow,
        )
        touches_trigger = _touches_level(out, trigger_price)
        out["signal"] = _build_intrabar_cross_signal(previous_diff, current_diff, touches_trigger)
        out.loc[out["signal"] == 1, "entry_trigger_price"] = trigger_price
        out.loc[out["signal"] == -1, "exit_trigger_price"] = trigger_price
        out["signal_price"] = np.where(
            out["signal"] == 1,
            out["entry_trigger_price"],
            np.where(out["signal"] == -1, out["exit_trigger_price"], np.nan),
        )
    else:
        out["_above"] = (current_diff > 0).astype(int)
        out["_prev_above"] = out["_above"].shift(1)
        out.loc[(out["_above"] == 1) & (out["_prev_above"] == 0), "signal"] = 1
        out.loc[(out["_above"] == 0) & (out["_prev_above"] == 1), "signal"] = -1
        out["signal_price"] = out["close"].where(out["signal"] != 0)
        out = out.drop(columns=["_above", "_prev_above"])

    if log_fn:
        buys = (out["signal"] == 1).sum()
        sells = (out["signal"] == -1).sum()
        log_fn(f"[strategy] MACD → {buys} buy signals, {sells} sell signals")

    return out


STRATEGIES = {
    "ema_crossover": ema_crossover,
    "rsi_mean_reversion": rsi_mean_reversion,
    "breakout": breakout,
    "macd": macd,
}


def run_strategy(
    df: pd.DataFrame,
    strategy_name: str,
    params: Dict[str, Any],
    execution_mode: str = "on_close",
    log_fn: Optional[Callable] = None,
) -> pd.DataFrame:
    """Dispatch to the correct strategy function."""
    if strategy_name not in STRATEGIES:
        raise ValueError(f"Unknown strategy '{strategy_name}'. Available: {list(STRATEGIES.keys())}")

    fn = STRATEGIES[strategy_name]
    return fn(df, **params, execution_mode=execution_mode, log_fn=log_fn)
