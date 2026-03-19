"""
history_manager.py
Manages SQLite database for storing backtest history.
"""

import sqlite3
import json
import os
from typing import List, Dict, Any
import config

DB_PATH = os.path.join(config.DATA_DIR, "history.db")


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def _json_load(value: Any, fallback: Any):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _normalize_history_result(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return a frontend-friendly payload for a stored backtest row."""
    parameters = _json_load(row.get("parameters"), {})
    metrics = _json_load(row.get("metrics"), {})
    trades = _json_load(row.get("trades"), [])
    results_json = _json_load(row.get("results_json"), None)

    if isinstance(results_json, dict):
        result = dict(results_json)
        result.setdefault("symbol", row.get("symbol"))
        result.setdefault("strategy", row.get("strategy"))
        result.setdefault("interval", row.get("interval"))
        result.setdefault("start", row.get("start_date"))
        result.setdefault("end", row.get("end_date"))
        result.setdefault("strategy_params", parameters)
        result.setdefault("metrics", metrics)
        result.setdefault("trades", trades)
        result.setdefault("equity_curve", [])
        result.setdefault("drawdown_series", [])
        result.setdefault("indicator_data", {})
        result["history_id"] = row.get("id")
        result["timestamp"] = row.get("timestamp")
        result["history_summary_only"] = False
        return result

    return {
        "history_id": row.get("id"),
        "timestamp": row.get("timestamp"),
        "symbol": row.get("symbol"),
        "strategy": row.get("strategy"),
        "interval": row.get("interval"),
        "start": row.get("start_date"),
        "end": row.get("end_date"),
        "strategy_params": parameters,
        "metrics": metrics,
        "trades": trades,
        "equity_curve": [],
        "drawdown_series": metrics.get("drawdown_series", []),
        "indicator_data": {},
        "total_bars": None,
        "execution_mode": None,
        "history_summary_only": True,
    }


def init_db():
    """Initialize the SQLite database and create the backtests table."""
    if not os.path.exists(config.DATA_DIR):
        os.makedirs(config.DATA_DIR)
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backtests (
            id TEXT PRIMARY KEY,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT,
            strategy TEXT,
            interval TEXT,
            start_date TEXT,
            end_date TEXT,
            parameters TEXT,
            metrics TEXT,
            trades TEXT,
            results_json TEXT
        )
    """)
    columns = _table_columns(conn, "backtests")
    if "results_json" not in columns:
        cursor.execute("ALTER TABLE backtests ADD COLUMN results_json TEXT")
    conn.commit()
    conn.close()

def save_backtest(task_id: str, results: Dict[str, Any]):
    """Save backtest results to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Extract data from results
    symbol = results.get("symbol")
    strategy = results.get("strategy")
    interval = results.get("interval")
    start_date = results.get("start")
    end_date = results.get("end")
    
    # Serialize complex objects
    params_json = json.dumps(results.get("strategy_params", {}))
    metrics_json = json.dumps(results.get("metrics", {}))
    # We might not want to store thousands of trades in SQLite if it gets too big, 
    # but for this requirement, we'll store them.
    trades_json = json.dumps(results.get("trades", []))
    results_json = json.dumps(results)
    
    cursor.execute("""
        INSERT INTO backtests (id, symbol, strategy, interval, start_date, end_date, parameters, metrics, trades, results_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (task_id, symbol, strategy, interval, start_date, end_date, params_json, metrics_json, trades_json, results_json))
    
    conn.commit()
    conn.close()

def get_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve the recent backtest history."""
    if not os.path.exists(DB_PATH):
        return []
        
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, timestamp, symbol, strategy, interval, start_date, end_date, parameters, metrics
        FROM backtests
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    history = []
    for row in rows:
        item = dict(row)
        item["parameters"] = _json_load(item["parameters"], {})
        item["metrics"] = _json_load(item["metrics"], {})
        history.append(item)
        
    conn.close()
    return history

def get_backtest_details(task_id: str) -> Dict[str, Any]:
    """Retrieve full details of a specific backtest including trades."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM backtests WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return _normalize_history_result(dict(row))
    return None

# Initialize on import
init_db()
