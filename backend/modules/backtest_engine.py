"""
backtest_engine.py
Bar-by-bar backtesting with slippage, brokerage commissions, and position sizing.
Generates trade log, portfolio equity curve, and per-trade statistics.
"""

import pandas as pd
import numpy as np
from typing import Optional, Callable, Dict, Any, List, Tuple


def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float, max_fraction: float = 0.25) -> float:
    """Kelly Criterion: f* = (bp - q) / b where b = avg_win/avg_loss, p = win_rate."""
    if avg_loss == 0:
        return 0.0
    b = avg_win / avg_loss
    p = win_rate
    q = 1 - p
    kelly = (b * p - q) / b
    return max(0.0, min(kelly, max_fraction))


def compute_position_size(
    capital: float,
    price: float,
    method: str = "pct_capital",
    pct: float = 10.0,
    fixed_units: int = 100,
    win_rate: float = 0.5,
    avg_win: float = 1.0,
    avg_loss: float = 1.0,
) -> int:
    """
    Calculate number of shares to buy.
    method: 'fixed' | 'pct_capital' | 'kelly'
    """
    if price <= 0:
        return 0

    if method == "fixed":
        return fixed_units
    elif method == "pct_capital":
        allocation = capital * (pct / 100.0)
        return max(1, int(allocation / price))
    elif method == "kelly":
        f = kelly_fraction(win_rate, avg_win, avg_loss)
        allocation = capital * f
        return max(1, int(allocation / price))
    else:
        return max(1, int(capital * (pct / 100.0) / price))


VALID_EXECUTION_MODES = {"on_close", "intrabar"}


def _format_trade_date(value: Any) -> str:
    return str(value.date() if hasattr(value, "date") else value)


def _resolve_signal_price(row: pd.Series, signal: int, execution_mode: str) -> float:
    """Resolve the execution price for a non-stop signal."""
    close_price = float(row["close"])
    if execution_mode != "intrabar":
        return close_price

    open_raw = row.get("open", np.nan)
    open_price = float(open_raw) if pd.notna(open_raw) else close_price

    if signal == 1:
        trigger_price = row.get("entry_trigger_price", np.nan)
        if pd.notna(trigger_price):
            return max(open_price, float(trigger_price))
    elif signal == -1:
        trigger_price = row.get("exit_trigger_price", np.nan)
        if pd.notna(trigger_price):
            return min(open_price, float(trigger_price))

    signal_price = row.get("signal_price", np.nan)
    if pd.notna(signal_price):
        return float(signal_price)

    return close_price


def _finalize_trade(
    entry_date: Any,
    exit_date: Any,
    entry_price: float,
    exit_price: float,
    shares: int,
    entry_commission: float,
    exit_commission: float,
    trade_type: str,
) -> Tuple[Dict[str, Any], float, float]:
    """Build a completed trade and return the trade, net pnl, and exit proceeds."""
    entry_value = (shares * entry_price) + entry_commission
    proceeds = (shares * exit_price) - exit_commission
    pnl = proceeds - entry_value
    pnl_pct = (pnl / entry_value * 100.0) if entry_value > 0 else 0.0

    trade = {
        "entry_date": _format_trade_date(entry_date),
        "exit_date": _format_trade_date(exit_date),
        "entry_price": round(entry_price, 4),
        "exit_price": round(exit_price, 4),
        "shares": shares,
        "entry_commission": round(entry_commission, 4),
        "exit_commission": round(exit_commission, 4),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 4),
        "type": trade_type,
    }
    return trade, pnl, proceeds


def run_backtest(
    df: pd.DataFrame,
    initial_capital: float = 100_000.0,
    slippage_pct: float = 0.05,
    commission: float = 10.0,
    execution_mode: str = "on_close",
    position_sizing: str = "pct_capital",
    position_pct: float = 20.0,
    fixed_units: int = 100,
    stop_loss_pct: Optional[float] = None,
    stop_loss_atr_mult: Optional[float] = None,
    log_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    Run a backtest on a DataFrame with a 'signal' column.

    Parameters
    ----------
    df              : OHLCV DataFrame with 'signal' column (1=buy, -1=sell)
    initial_capital : Starting portfolio value
    slippage_pct    : Slippage as % of price (applied each side)
    commission      : Flat commission per trade in currency
    execution_mode  : 'on_close' | 'intrabar' (fills immediately at trigger when available)
    position_sizing : 'fixed' | 'pct_capital' | 'kelly'
    position_pct    : % of capital per trade (for pct_capital mode)
    fixed_units     : Fixed number of shares (for fixed mode)
    stop_loss_pct   : Optional stop-loss % from entry price
    stop_loss_atr_mult : Optional stop-loss ATR multiplier
    log_fn          : Progress logging callback

    Returns
    -------
    dict with: trades, portfolio, equity_curve, metrics_inputs
    """
    if "signal" not in df.columns:
        raise ValueError("DataFrame must have a 'signal' column. Run a strategy first.")
    if execution_mode not in VALID_EXECUTION_MODES:
        raise ValueError(f"Unknown execution_mode '{execution_mode}'. Available: {sorted(VALID_EXECUTION_MODES)}")
    if df.empty:
        raise ValueError("DataFrame is empty. Load data before running backtest.")

    if log_fn:
        log_fn(f"[backtest] Starting simulation | capital={initial_capital:,.0f} | execution={execution_mode}")

    df = df.sort_index().copy()
    trades: List[Dict] = []
    capital = initial_capital
    portfolio_values = []
    holdings = 0       # shares held
    entry_price = 0.0
    entry_date = None
    entry_commission = 0.0
    in_position = False
    stop_price = 0.0

    # Rolling win stats for Kelly sizing (initialized with defaults)
    recent_wins = [1.0] * 10
    recent_losses = [1.0] * 10

    slip = slippage_pct / 100.0
    
    # Calculate ATR if needed
    if stop_loss_atr_mult is not None and "atr" not in df.columns:
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift(1)).abs()
        low_close = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.ewm(span=14, adjust=False).mean()

    for date, row in df.iterrows():
        sig = int(row["signal"]) if pd.notna(row["signal"]) else 0
        close_price = float(row["close"])
        stop_triggered = False

        # --- Check stop loss ---
        if in_position and stop_price > 0:
            if row["low"] <= stop_price:
                # Force exit at stop price (or open if gapped down below stop price)
                open_raw = row.get("open", np.nan)
                open_price = float(open_raw) if pd.notna(open_raw) else stop_price
                actual_exit_price = min(open_price, stop_price)
                exit_price = actual_exit_price * (1 - slip)
                trade, pnl, proceeds = _finalize_trade(
                    entry_date=entry_date,
                    exit_date=date,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    shares=holdings,
                    entry_commission=entry_commission,
                    exit_commission=commission,
                    trade_type="STOP LOSS",
                )
                trades.append(trade)
                capital += proceeds
                if pnl >= 0:
                    recent_wins.append(pnl)
                else:
                    recent_losses.append(abs(pnl))
                holdings = 0
                in_position = False
                stop_price = 0.0
                entry_commission = 0.0
                stop_triggered = True

        # --- Buy signal ---
        if not stop_triggered and sig == 1 and not in_position:
            trade_price = _resolve_signal_price(row, sig, execution_mode)
            avg_win = np.mean(recent_wins[-20:]) if recent_wins else 1.0
            avg_loss = np.mean(recent_losses[-20:]) if recent_losses else 1.0
            win_rate = len([x for x in recent_wins if x > 0]) / max(1, len(recent_wins) + len(recent_losses))
            shares = compute_position_size(
                capital=capital,
                price=trade_price,
                method=position_sizing,
                pct=position_pct,
                fixed_units=fixed_units,
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
            )
            buy_price = trade_price * (1 + slip)
            cost = shares * buy_price + commission
            if cost <= capital and shares > 0:
                capital -= cost
                holdings = shares
                entry_price = buy_price
                entry_date = date
                entry_commission = commission
                in_position = True
                
                if stop_loss_pct:
                    stop_price = entry_price * (1 - stop_loss_pct / 100.0)
                elif stop_loss_atr_mult and "atr" in row:
                    stop_price = entry_price - (row["atr"] * stop_loss_atr_mult)
                else:
                    stop_price = 0.0
                    
                if log_fn and len(trades) < 5:  # log first few for visibility
                    log_fn(f"[backtest] BUY  {shares} shares @ {buy_price:.2f} on {_format_trade_date(date)}")

        # --- Sell signal ---
        elif not stop_triggered and sig == -1 and in_position:
            trade_price = _resolve_signal_price(row, sig, execution_mode)
            exit_price = trade_price * (1 - slip)
            trade, pnl, proceeds = _finalize_trade(
                entry_date=entry_date,
                exit_date=date,
                entry_price=entry_price,
                exit_price=exit_price,
                shares=holdings,
                entry_commission=entry_commission,
                exit_commission=commission,
                trade_type="LONG",
            )
            capital += proceeds
            trades.append(trade)

            if pnl >= 0:
                recent_wins.append(pnl)
            else:
                recent_losses.append(abs(pnl))

            if log_fn and len(trades) <= 5:
                log_fn(f"[backtest] SELL {holdings} shares @ {exit_price:.2f} | PnL: {pnl:+.2f} ({trade['pnl_pct']:+.2f}%)")

            holdings = 0
            in_position = False
            stop_price = 0.0
            entry_commission = 0.0

        portfolio_val = capital + (holdings * close_price if in_position else 0.0)
        portfolio_values.append({"date": _format_trade_date(date), "value": round(portfolio_val, 2)})

    # Close any open position at last bar
    if in_position:
        last_price = df["close"].iloc[-1]
        exit_price = last_price * (1 - slip)
        trade, _, proceeds = _finalize_trade(
            entry_date=entry_date,
            exit_date=df.index[-1],
            entry_price=entry_price,
            exit_price=exit_price,
            shares=holdings,
            entry_commission=entry_commission,
            exit_commission=commission,
            trade_type="FORCED EXIT",
        )
        capital += proceeds
        trades.append(trade)
        holdings = 0
        in_position = False
        stop_price = 0.0
        entry_commission = 0.0
        portfolio_values[-1]["value"] = round(capital, 2)

    if log_fn:
        log_fn(f"[backtest] Simulation complete | {len(trades)} trades executed")
        log_fn(f"[backtest] Final capital: {capital:,.2f}")

    # Build equity curve
    final_value = capital

    return {
        "trades": trades,
        "equity_curve": portfolio_values,
        "initial_capital": initial_capital,
        "final_value": round(final_value, 2),
        "total_trades": len(trades),
    }
