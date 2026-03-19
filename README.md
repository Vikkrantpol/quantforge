# QuantForge

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)
![Tests](https://img.shields.io/badge/tests-83%20passed-22C55E)
![License](https://img.shields.io/badge/license-MIT-111827)

QuantForge is a full-stack trading research platform for running systematic backtests, downloading OHLCV data, reviewing performance analytics, and iterating on trading ideas from a single dark-terminal style UI.

Created and led by **Vikkrant**.

## What It Does

- Run backtests with live progress logs and saved result history.
- Download market data from Yahoo Finance, broker integrations, or CSV files.
- Test multiple strategies with configurable execution assumptions.
- Inspect equity, drawdown, trade logs, and portfolio statistics in a dedicated results workspace.
- Persist research sessions locally so prior runs can be reopened from History.

## Core Features

### Quant Lab

- Backtest form for symbol, period, interval, data source, strategy, and execution settings.
- Custom date ranges, multiple position sizing models, slippage, commissions, and stop-loss support.
- Intrabar-aware execution for breakout logic and estimated intrabar crossover handling for EMA and MACD modes.

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

- Yahoo Finance as the default market data source
- CSV-based local datasets
- Broker-aware download and validation plumbing
- Sample datasets for equities and crypto research

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
| Backend | Python, FastAPI, Pandas, NumPy, httpx, yfinance |
| Frontend | React 18, Vite, Axios, Recharts, Lucide |
| Broker SDKs | FYERS API v3 |
| Storage | Local files and SQLite history |
| UI | Custom CSS with terminal-inspired styling |

## Credit

QuantForge was created by **Vikkrant**. All product direction, concept ownership, and project credit belong to him.

## License

MIT. See [LICENSE](./LICENSE).

<sub>broker note: broker connectivity is present, but fyers live validation still needs a follow-up pass.</sub>
