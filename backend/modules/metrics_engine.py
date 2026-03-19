"""
metrics_engine.py
Computes all performance metrics from the backtest results.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional


def _equity_to_returns(equity_curve: List[Dict]) -> np.ndarray:
    """Convert equity curve [{date, value}] to daily return series."""
    values = np.array([p["value"] for p in equity_curve], dtype=float)
    returns = np.diff(values) / values[:-1]
    return returns


def compute_cagr(initial: float, final: float, years: float) -> float:
    """Compound Annual Growth Rate."""
    if years <= 0 or initial <= 0:
        return 0.0
    return (final / initial) ** (1 / years) - 1


def compute_max_drawdown(equity_curve: List[Dict]) -> Dict[str, Any]:
    """Max drawdown as percentage and duration."""
    values = np.array([p["value"] for p in equity_curve], dtype=float)
    dates = [p["date"] for p in equity_curve]

    peak = values[0]
    max_dd = 0.0
    max_dd_start = dates[0]
    max_dd_end = dates[0]
    current_peak_date = dates[0]
    dd_series = []

    for i, v in enumerate(values):
        if v > peak:
            peak = v
            current_peak_date = dates[i]
        dd = (v - peak) / peak
        dd_series.append({"date": dates[i], "drawdown": round(dd * 100, 4)})
        if dd < max_dd:
            max_dd = dd
            max_dd_start = current_peak_date
            max_dd_end = dates[i]

    return {
        "max_drawdown_pct": round(max_dd * 100, 4),
        "max_dd_start": max_dd_start,
        "max_dd_end": max_dd_end,
        "drawdown_series": dd_series,
    }


def compute_sharpe(returns: np.ndarray, risk_free_rate: float = 0.05, periods_per_year: int = 252) -> float:
    """Annualized Sharpe Ratio."""
    if len(returns) < 2:
        return 0.0
    rf_daily = (1 + risk_free_rate) ** (1 / periods_per_year) - 1
    excess = returns - rf_daily
    std = np.std(excess, ddof=1)
    if std == 0:
        return 0.0
    return float(np.mean(excess) / std * np.sqrt(periods_per_year))


def compute_sortino(returns: np.ndarray, risk_free_rate: float = 0.05, periods_per_year: int = 252) -> float:
    """Annualized Sortino Ratio (penalizes only downside volatility)."""
    if len(returns) < 2:
        return 0.0
    rf_daily = (1 + risk_free_rate) ** (1 / periods_per_year) - 1
    excess = returns - rf_daily
    downside = returns[returns < 0]
    if len(downside) == 0:
        return float("inf")
    downside_std = np.std(downside, ddof=1)
    if downside_std == 0:
        return 0.0
    return float(np.mean(excess) / downside_std * np.sqrt(periods_per_year))


def compute_calmar(cagr: float, max_dd_pct: float) -> float:
    """Calmar Ratio = CAGR / |Max Drawdown|."""
    if max_dd_pct == 0:
        return 0.0
    return cagr / abs(max_dd_pct / 100)


def compute_trade_stats(trades: List[Dict]) -> Dict[str, Any]:
    """Win rate, expectancy, avg win/loss, profit factor."""
    if not trades:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "largest_win": 0.0,
            "largest_loss": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "avg_trade_pnl": 0.0,
            "total_pnl": 0.0,
            "avg_holding_bars": 0,
        }

    pnls = [t["pnl"] for t in trades]
    pnl_pcts = [t["pnl_pct"] for t in trades]
    wins = [p for p in pnls if p >= 0]
    losses = [p for p in pnls if p < 0]

    win_rate = len(wins) / len(pnls) if pnls else 0
    avg_win = np.mean(wins) if wins else 0.0
    avg_loss = abs(np.mean(losses)) if losses else 0.0
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
    profit_factor = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else float("inf")

    return {
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(win_rate * 100, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "largest_win": round(max(pnls), 2) if pnls else 0.0,
        "largest_loss": round(min(pnls), 2) if pnls else 0.0,
        "expectancy": round(expectancy, 2),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else 999.0,
        "avg_trade_pnl": round(np.mean(pnls), 2) if pnls else 0.0,
        "total_pnl": round(sum(pnls), 2),
        "avg_pnl_pct": round(np.mean(pnl_pcts), 4) if pnl_pcts else 0.0,
    }


def compute_volatility(returns: np.ndarray, periods_per_year: int = 252) -> float:
    """Annualized volatility of returns."""
    if len(returns) < 2:
        return 0.0
    return float(np.std(returns, ddof=1) * np.sqrt(periods_per_year))


def compute_var(returns: np.ndarray, confidence: float = 0.95) -> float:
    """Value at Risk (historical) at given confidence level."""
    if len(returns) < 10:
        return 0.0
    return float(np.percentile(returns, (1 - confidence) * 100))


def compute_all_metrics(
    equity_curve: List[Dict],
    trades: List[Dict],
    initial_capital: float,
    final_value: float,
    risk_free_rate: float = 0.05,
    periods_per_year: int = 252,
) -> Dict[str, Any]:
    """
    Compute all performance metrics in one call.
    """
    returns = _equity_to_returns(equity_curve)

    # Calendar time
    if len(equity_curve) >= 2:
        try:
            start = pd.to_datetime(equity_curve[0]["date"])
            end = pd.to_datetime(equity_curve[-1]["date"])
            years = max((end - start).days / 365.25, 1 / 365.25)
        except Exception:
            years = len(equity_curve) / periods_per_year
    else:
        years = 1.0

    cagr = compute_cagr(initial_capital, final_value, years)
    dd_info = compute_max_drawdown(equity_curve)
    sharpe = compute_sharpe(returns, risk_free_rate, periods_per_year)
    sortino = compute_sortino(returns, risk_free_rate, periods_per_year)
    calmar = compute_calmar(cagr, dd_info["max_drawdown_pct"])
    vol = compute_volatility(returns, periods_per_year)
    var95 = compute_var(returns, 0.95)
    trade_stats = compute_trade_stats(trades)

    total_return = (final_value - initial_capital) / initial_capital * 100

    return {
        "total_return_pct": round(total_return, 4),
        "cagr_pct": round(cagr * 100, 4),
        "max_drawdown_pct": dd_info["max_drawdown_pct"],
        "max_dd_start": dd_info["max_dd_start"],
        "max_dd_end": dd_info["max_dd_end"],
        "sharpe_ratio": round(sharpe, 4),
        "sortino_ratio": round(sortino, 4),
        "calmar_ratio": round(calmar, 4),
        "annualized_volatility_pct": round(vol * 100, 4),
        "var_95_pct": round(var95 * 100, 4),
        "initial_capital": initial_capital,
        "final_value": round(final_value, 2),
        "years_backtested": round(years, 2),
        "drawdown_series": dd_info["drawdown_series"],
        **trade_stats,
    }
