# QuantForge: Multi-Market-Multi-Asset Algo Strategy Lab

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)
![Markets](https://img.shields.io/badge/Markets-India%20%7C%20US%20%7C%20Crypto-0EA5E9)
![Assets](https://img.shields.io/badge/Assets-Equities%20%7C%20Crypto-14B8A6)
![Storage](https://img.shields.io/badge/Storage-SQLite-003B57?logo=sqlite&logoColor=white)
![Tests](https://img.shields.io/badge/tests-83%20passed-22C55E)
![License](https://img.shields.io/badge/license-MIT-111827)

> Multi-asset-Multi Market-Multi strategy all in one backtesting algo trading research platform.

QuantForge is a full-stack, multi-market, multi-asset strategy research platform built for backtesting equities and crypto across multiple timeframes, time periods, and strategy styles from one unified interface.

Built by **Vikkrant**.

## Strongest Positioning

- Multi-market: India, US, crypto
- Multi-asset: equities and crypto
- Multi-timeframe: intraday and daily research
- Multi-period: fixed periods and custom date ranges
- Multi-strategy: EMA, RSI, breakout, MACD, and an extensible strategy engine
- Persistent research stack: results and history stored locally in SQLite
- Full-stack workflow: data, backtest, analytics, history, and broker connectivity in one product

## What It Does

- Run backtests with live progress logs and saved result history.
- Research across multiple markets and instrument types from one workspace.
- Test multiple strategies with configurable execution assumptions.
- Inspect equity, drawdown, trade logs, and portfolio statistics in a dedicated results workspace.
- Persist research sessions locally so prior runs can be reopened from History with SQLite-backed storage.

## Core Features

### Quant Lab

- Backtest form for symbol, period, interval, data source, strategy, and execution settings across multi-market workflows.
- Custom date ranges, multiple position sizing models, slippage, commissions, and stop-loss support.
- Intrabar-aware execution for breakout logic and estimated intrabar crossover handling for EMA and MACD modes.
- Built to handle research across Indian markets, US markets, and crypto symbols from the same product surface.

### Strategies

- EMA Crossover
- RSI Mean Reversion
- Breakout (Donchian)
- MACD

### Performance Analytics

- Total return
- CAGR
- Max drawdown
- Sharpe ratio
- Sortino ratio
- Calmar ratio
- Win rate
- Expectancy
- Profit factor
- VaR 95%
- Annualized volatility
- Full trade log and PnL history

### Data Support

- Multi-market data ingestion with broker-aware and CSV-driven research paths
- CSV-based local datasets
- Local history persistence through SQLite
- Broker support spanning Indian and US market workflows
- Sample datasets for equities and crypto research

<sub>QuantForge can also pull market data through yfinance when needed, but the platform is positioned as a broader multi-source research stack, not a single-provider tool.</sub>

### Research Workflow

- Recent run history in the sidebar
- Reopen saved reports from History
- Export results as JSON
- API-backed job progress terminal

## Architecture Docs

- [architectur.txt](./architectur.txt)
- [architecture_block_diagram.md](./architecture_block_diagram.md)

## Quick Start

```bash
chmod +x run.sh
./run.sh
```

Local services:

- UI: `http://localhost:5173`
- API: `http://localhost:8010`
- API docs: `http://localhost:8010/docs`

## Manual Setup

### Requirements

- Python 3.10+
- Node.js 18+

### Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r backend/requirements.txt
python3 backend/generate_sample_data.py
cd backend
python3 -m uvicorn main:app --reload --port 8010
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Environment Setup

Copy the template and keep secrets local:

```bash
cp .env.example .env
```

Important variables:

- `PORT=8010`
- `FRONTEND_URL=http://localhost:5173`
- `ALPACA_*` for Alpaca
- `KITE_*` for Zerodha
- `FYERS_*` for FYERS

`.env` is intentionally ignored by git.

## API Overview

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| GET | `/api/symbols` | Popular symbol list |
| POST | `/api/backtest` | Start a backtest job |
| GET | `/api/backtest/{id}/status` | Poll job progress and logs |
| GET | `/api/backtest/{id}/results` | Fetch completed results |
| POST | `/api/download-data` | Start an OHLCV download job |
| GET | `/api/download-data/{id}/status` | Poll download progress |
| GET | `/api/download-data/{id}/csv` | Download CSV output |
| GET | `/api/sample-data` | List bundled sample CSVs |
| GET | `/api/history` | List saved backtest summaries |
| GET | `/api/history/{id}` | Load a saved result payload |

## Sample Datasets

Bundled data includes:

- `AAPL_sample.csv`
- `MSFT_sample.csv`
- `TSLA_sample.csv`
- `GOOGL_sample.csv`
- `SPY_sample.csv`
- `RELIANCE_sample.csv`
- `BTC-USD_sample.csv`

These are useful for validating strategy logic and UI behavior without waiting on external providers.

## Project Structure

```text
Backtesting_trading-platform/
|- .env.example
|- .gitignore
|- LICENSE
|- CONTRIBUTING.md
|- README.md
|- architectur.txt
|- architecture_block_diagram.md
|- run.sh
|- backend/
|  |- main.py
|  |- config.py
|  |- api/routes.py
|  |- modules/
|  |  |- backtest_engine.py
|  |  |- broker_connector.py
|  |  |- data_ingestion.py
|  |  |- history_manager.py
|  |  |- metrics_engine.py
|  |  |- strategy_engine.py
|  |- tests/test_all.py
|- frontend/
|  |- package.json
|  |- vite.config.js
|  |- src/
|  |  |- App.jsx
|  |  |- api/client.js
|  |  |- components/
```

## Testing

Backend regression suite:

```bash
./.venv/bin/python -m pytest backend/tests/test_all.py -q
```

Frontend production build:

```bash
cd frontend
npm run build
```

Current backend coverage includes `83` passing tests across data ingestion, strategy rules, execution logic, metrics, history, and API behavior.

## Tech Stack

| Layer | Tools |
| --- | --- |
| Backend | Python, FastAPI, Pandas, NumPy, httpx |
| Frontend | React 18, Vite, Axios, Recharts, Lucide |
| Broker SDKs | FYERS API v3 and broker integration adapters |
| Storage | SQLite-backed local history and research state |
| UI | Custom CSS with terminal-inspired styling |

## Credit

QuantForge was created, designed, and built by **Vikkrant**. The product vision, system direction, and project credit belong to him.

## License

MIT. See [LICENSE](./LICENSE).
