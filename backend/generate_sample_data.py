"""
generate_sample_data.py
Generates synthetic but realistic OHLCV data for testing.
Uses Geometric Brownian Motion (GBM) with realistic volume patterns.
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

np.random.seed(42)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def generate_gbm_ohlcv(
    symbol: str,
    start_date: str = "2020-01-01",
    days: int = 1260,        # ~5 years of trading days
    initial_price: float = 150.0,
    mu: float = 0.0003,      # daily drift
    sigma: float = 0.018,    # daily volatility
    initial_volume: float = 5_000_000,
) -> pd.DataFrame:
    """
    Generate realistic OHLCV using GBM with:
    - Mean-reverting volatility (GARCH-lite)
    - Realistic open gaps
    - Volume correlated with price moves
    - Occasional gap-up / gap-down events
    """
    print(f"Generating {days} bars for {symbol} starting at ${initial_price}")

    # Business day calendar
    dates = pd.date_range(start=start_date, periods=days, freq="B")

    # GBM price path
    dt = 1
    vol = sigma
    closes = [initial_price]
    vols = [sigma]

    for i in range(days - 1):
        # GARCH-lite: vol reverts to sigma
        prev_vol = vols[-1]
        shock = np.random.normal(0, 1)
        new_vol = max(0.005, 0.85 * prev_vol + 0.10 * sigma + 0.05 * abs(shock) * prev_vol)
        vols.append(new_vol)

        # Occasional gap events (earnings, news)
        gap = 0.0
        if np.random.random() < 0.01:  # 1% chance of big gap
            gap = np.random.normal(0, 0.04)

        ret = np.random.normal(mu, new_vol) + gap
        closes.append(max(1.0, closes[-1] * np.exp(ret)))

    closes = np.array(closes)

    # Build OHLCV
    records = []
    for i, (date, close) in enumerate(zip(dates, closes)):
        prev_close = closes[i - 1] if i > 0 else close

        # Open: gap from previous close (realistic overnight gap)
        open_gap = np.random.normal(0, vols[i] * 0.3)
        open_p = prev_close * np.exp(open_gap)

        # Intraday high/low
        intraday_range = abs(np.random.normal(0, vols[i] * 1.5))
        high = max(open_p, close) * (1 + intraday_range * np.random.uniform(0.3, 1.0))
        low = min(open_p, close) * (1 - intraday_range * np.random.uniform(0.3, 1.0))

        # Volume: higher on big moves, log-normal base
        price_move = abs(close / prev_close - 1)
        vol_multiplier = 1 + price_move * 20  # big moves = high volume
        volume = int(np.random.lognormal(
            np.log(initial_volume),
            0.5
        ) * vol_multiplier)

        records.append({
            "Date": date.date(),
            "Open": round(float(open_p), 2),
            "High": round(float(high), 2),
            "Low": round(float(low), 2),
            "Close": round(float(close), 2),
            "Volume": max(10000, volume),
        })

    df = pd.DataFrame(records)
    df = df.set_index("Date")

    # Sanity check: high >= max(open, close), low <= min(open, close)
    df["High"] = df[["High", "Open", "Close"]].max(axis=1)
    df["Low"] = df[["Low", "Open", "Close"]].min(axis=1)

    return df


SYMBOLS = [
    ("AAPL",     "2020-01-01", 1260, 175.0,  0.0004, 0.019, 80_000_000),
    ("MSFT",     "2020-01-01", 1260, 220.0,  0.0005, 0.017, 30_000_000),
    ("TSLA",     "2020-01-01", 1260,  80.0,  0.0008, 0.038, 90_000_000),
    ("GOOGL",    "2020-01-01", 1260, 140.0,  0.0004, 0.018, 25_000_000),
    ("SPY",      "2020-01-01", 1260, 320.0,  0.0003, 0.012, 70_000_000),
    ("RELIANCE", "2020-01-01", 1260,1800.0,  0.0003, 0.016, 10_000_000),
    ("BTC-USD",  "2020-01-01", 1260,9000.0,  0.0010, 0.045,  5_000_000),
]


if __name__ == "__main__":
    for symbol, start, days, price, mu, sigma, vol in SYMBOLS:
        df = generate_gbm_ohlcv(symbol, start, days, price, mu, sigma, vol)
        path = os.path.join(OUTPUT_DIR, f"{symbol}_sample.csv")
        df.to_csv(path)
        print(f"  Saved {len(df)} rows → {path}")
    print("\nAll sample data generated!")
