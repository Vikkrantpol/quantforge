# QuantForge Block Diagram

```mermaid
flowchart LR
    U["User"] --> FE["React + Vite Frontend\nApp.jsx / QuantLab / Results / History"]

    FE --> API["FastAPI Backend\nbackend/main.py + backend/api/routes.py"]

    API --> DI["Data Ingestion\nCSV / yfinance / broker adapters"]
    API --> SE["Strategy Engine\nEMA / RSI / Breakout / MACD"]
    API --> BE["Backtest Engine\nfills / slippage / commission / sizing / stops"]
    API --> ME["Metrics Engine\nreturn / drawdown / Sharpe / trade stats"]
    API --> HM["History Manager\nSQLite persistence"]

    DI --> YF["Yahoo Finance"]
    DI --> BR["Broker APIs\nAlpaca / Zerodha / Fyers"]
    DI --> CSV["Local CSV Files"]

    HM --> DB["SQLite\nbackend/data/history.db"]
    DI --> SAMPLES["Sample Data\nbackend/data/*.csv"]
    API --> TEMP["Downloaded CSV Output\nbackend/temp/*.csv"]

    SE --> BE
    BE --> ME
    ME --> HM
    HM --> API
    API --> FE
```

## Notes

- `POST /api/backtest` drives the main research flow.
- `POST /api/download-data` drives CSV export flow.
- Active task progress is kept in the backend process; completed results are stored in SQLite.
- `intrabar` execution is an OHLC-based approximation, not a tick replay engine.
