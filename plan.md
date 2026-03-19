# QuantForge — Trading Research Platform
## Plan, Assumptions & Implementation Guide

---

## Assumptions
- macOS with Python 3.10+ and Node 18+ installed
- All computation is local (no cloud required)
- Broker connection is **optional** — yfinance is the default data source
- Backtesting is vectorized (fast) not event-driven (simpler, sufficient for daily/hourly data)
- Supported brokers: Alpaca (US stocks), Zerodha/Kite (Indian markets)
- OHLCV data granularity: 1m, 5m, 15m, 1h, 1d
- Strategies: EMA Crossover, RSI Mean Reversion, Breakout (N-day high/low)
- Position sizing: Fixed units, % of capital, Kelly Criterion
- SSE/polling for live progress updates in terminal UI

---

## File Structure

```
trading-platform/
├── plan.md                        ← You are here
├── README.md                      ← Setup & usage
├── run.sh                         ← Single-command launcher
├── .env.example                   ← Environment variables template
│
├── backend/
│   ├── requirements.txt
│   ├── main.py                    ← FastAPI entrypoint
│   ├── config.py                  ← Settings & env loading
│   ├── generate_sample_data.py    ← Generates sample CSVs
│   │
│   ├── modules/
│   │   ├── __init__.py
│   │   ├── data_ingestion.py      ← CSV / yfinance / broker data loading
│   │   ├── strategy_engine.py     ← EMA, RSI, Breakout signals
│   │   ├── backtest_engine.py     ← Simulation: slippage, commission, sizing
│   │   ├── metrics_engine.py      ← CAGR, Sharpe, Sortino, drawdown, etc.
│   │   └── broker_connector.py   ← Optional Alpaca / Zerodha adapter
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py             ← All REST endpoints
│   │
│   ├── data/
│   │   ├── AAPL_sample.csv
│   │   ├── MSFT_sample.csv
│   │   └── RELIANCE_sample.csv
│   │
│   └── tests/
│       ├── __init__.py
│       ├── test_data_ingestion.py
│       ├── test_strategy_engine.py
│       ├── test_backtest_engine.py
│       ├── test_metrics_engine.py
│       └── run_all_tests.sh
│
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── index.css              ← Global dark terminal CSS
        ├── api/
        │   └── client.js         ← Axios API client
        ├── hooks/
        │   └── useBacktest.js    ← Polling hook
        └── components/
            ├── Sidebar.jsx
            ├── Dashboard.jsx
            ├── QuantLab.jsx       ← Main research page
            ├── ProgressTerminal.jsx
            ├── MetricsGrid.jsx
            ├── EquityCurveChart.jsx
            ├── DrawdownChart.jsx
            ├── TradeLog.jsx
            └── BrokerConfig.jsx
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/health | Health check |
| POST | /api/backtest | Start backtest, returns backtest_id |
| GET | /api/backtest/{id}/status | Poll progress logs |
| GET | /api/backtest/{id}/results | Fetch full results |
| POST | /api/download-data | Fetch & save OHLCV data |
| GET | /api/download-data/{id}/status | Download task status |
| GET | /api/download-data/{id}/csv | Return CSV bytes |
| POST | /api/validate-broker | Test broker connection |
| GET | /api/symbols | Popular symbols list |

---

## Implementation Phases

### Phase 1 — Backend Core
- [x] FastAPI app with CORS
- [x] data_ingestion.py (CSV + yfinance)
- [x] strategy_engine.py (EMA, RSI, Breakout)
- [x] backtest_engine.py (vectorized simulation)
- [x] metrics_engine.py (all metrics)
- [x] broker_connector.py (Alpaca + Zerodha stubs)

### Phase 2 — REST API
- [x] All routes in routes.py
- [x] Background task management (async threading)
- [x] Progress log streaming via polling

### Phase 3 — Frontend
- [x] Vite + React setup
- [x] Dark terminal CSS with glassmorphism
- [x] QuantLab form (data source, strategy, params)
- [x] Live progress terminal
- [x] Results: metrics, equity curve, drawdown, trade log
- [x] Download buttons (CSV data + results)

### Phase 4 — Tests & Data
- [x] Pytest backend tests
- [x] Sample CSV generation (3 symbols × 3 years)
- [x] run.sh single-command launcher

---

## Strategy Logic Summary

### EMA Crossover
- Buy signal: fast EMA crosses above slow EMA
- Sell signal: fast EMA crosses below slow EMA
- Default: fast=12, slow=26

### RSI Mean Reversion
- Buy signal: RSI drops below oversold threshold (default: 30)
- Sell signal: RSI rises above overbought threshold (default: 70)
- Default: period=14, oversold=30, overbought=70

### Breakout (N-Day High/Low)
- Buy signal: close breaks above N-day rolling high
- Sell signal: close breaks below N-day rolling low
- Default: window=20

## Backtest Parameters
- Slippage: % of price applied to entry/exit (e.g., 0.05% each way)
- Commission: flat or per-share rate per trade
- Position sizing: Fixed units | % of capital | Kelly Criterion
- Stop loss: optional percentage stop on each trade
