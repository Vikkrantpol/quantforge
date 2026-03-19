"""
broker_connector.py
Optional broker integrations for live data fetching.
Currently supports: Alpaca (US), Zerodha/Kite (India), and FYERS.
Falls back gracefully if broker libraries aren't installed.
"""

import pandas as pd
from typing import Optional, Callable
from datetime import datetime


def normalize_fyers_access_token(client_id: str, access_token: str) -> str:
    token = (access_token or "").strip()
    client_id = (client_id or "").strip()

    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    if client_id and token.startswith(f"{client_id}:"):
        return token[len(client_id) + 1:].strip()

    return token


class AlpacaConnector:
    """
    Alpaca Markets connector for historical bar data.
    Requires: pip install alpaca-trade-api
    API keys from: https://alpaca.markets
    """

    def __init__(self, api_key: str, secret_key: str, base_url: str = "https://paper-api.alpaca.markets"):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url
        self._api = None

    def _connect(self):
        try:
            import alpaca_trade_api as tradeapi
            self._api = tradeapi.REST(self.api_key, self.secret_key, self.base_url)
        except ImportError:
            raise ImportError(
                "alpaca-trade-api not installed.\n"
                "Run: pip install alpaca-trade-api"
            )

    def validate(self) -> dict:
        """Test the API connection and return account info."""
        self._connect()
        try:
            account = self._api.get_account()
            return {
                "status": "connected",
                "broker": "alpaca",
                "account_id": account.id,
                "buying_power": float(account.buying_power),
                "portfolio_value": float(account.portfolio_value),
            }
        except Exception as e:
            return {"status": "error", "broker": "alpaca", "error": str(e)}

    def get_bars(
        self,
        symbol: str,
        start: str,
        end: str,
        timeframe: str = "1Day",
        log_fn: Optional[Callable] = None,
    ) -> pd.DataFrame:
        """Download OHLCV bars from Alpaca."""
        self._connect()

        # Map our timeframes to Alpaca format
        tf_map = {
            "1d": "1Day", "1h": "1Hour", "15m": "15Min",
            "5m": "5Min", "1m": "1Min",
        }
        alpaca_tf = tf_map.get(timeframe, timeframe)

        if log_fn:
            log_fn(f"[alpaca] Fetching {symbol} | {alpaca_tf} | {start} → {end}")

        try:
            bars = self._api.get_bars(
                symbol,
                alpaca_tf,
                start=start,
                end=end,
                adjustment="all",
            ).df

            if bars.empty:
                raise ValueError(f"No data returned from Alpaca for {symbol}")

            bars = bars.rename(columns={
                "open": "open", "high": "high", "low": "low",
                "close": "close", "volume": "volume",
            })
            bars.index.name = "Date"

            if log_fn:
                log_fn(f"[alpaca] Received {len(bars)} bars")
            return bars

        except Exception as e:
            if log_fn:
                log_fn(f"[alpaca] Error: {e}. Falling back to yfinance...")
            from backend.modules.data_ingestion import load_from_yfinance
            return load_from_yfinance(symbol, start, end, timeframe, log_fn)


class ZerodhaConnector:
    """
    Zerodha Kite Connect connector.
    Requires: pip install kiteconnect
    API keys from: https://kite.trade
    """

    def __init__(self, api_key: str, access_token: str):
        self.api_key = api_key
        self.access_token = access_token
        self._kite = None

    def _connect(self):
        try:
            from kiteconnect import KiteConnect
            self._kite = KiteConnect(api_key=self.api_key)
            self._kite.set_access_token(self.access_token)
        except ImportError:
            raise ImportError(
                "kiteconnect not installed.\n"
                "Run: pip install kiteconnect"
            )

    def validate(self) -> dict:
        """Test connection."""
        self._connect()
        try:
            profile = self._kite.profile()
            return {
                "status": "connected",
                "broker": "zerodha",
                "user_id": profile.get("user_id"),
                "user_name": profile.get("user_name"),
            }
        except Exception as e:
            return {"status": "error", "broker": "zerodha", "error": str(e)}

    def get_historical(
        self,
        symbol: str,
        start: str,
        end: str,
        interval: str = "day",
        exchange: str = "NSE",
        log_fn: Optional[Callable] = None,
    ) -> pd.DataFrame:
        """Download historical data from Zerodha Kite."""
        self._connect()

        # Kite intervals
        interval_map = {
            "1d": "day", "1h": "60minute", "15m": "15minute",
            "5m": "5minute", "1m": "minute",
        }
        kite_interval = interval_map.get(interval, interval)

        if log_fn:
            log_fn(f"[zerodha] Fetching {symbol}:{exchange} | {kite_interval} | {start} → {end}")

        try:
            # Get instrument token
            instruments = self._kite.instruments(exchange)
            token = None
            for inst in instruments:
                if inst["tradingsymbol"] == symbol:
                    token = inst["instrument_token"]
                    break
            if not token:
                raise ValueError(f"Symbol {symbol} not found on {exchange}")

            records = self._kite.historical_data(
                token,
                from_date=datetime.strptime(start, "%Y-%m-%d"),
                to_date=datetime.strptime(end, "%Y-%m-%d"),
                interval=kite_interval,
            )

            df = pd.DataFrame(records)
            df = df.rename(columns={"date": "Date"})
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date")
            df.columns = [c.lower() for c in df.columns]

            if log_fn:
                log_fn(f"[zerodha] Received {len(df)} bars")
            return df

        except Exception as e:
            if log_fn:
                log_fn(f"[zerodha] Error: {e}. Falling back to yfinance...")
            from backend.modules.data_ingestion import load_from_yfinance
            return load_from_yfinance(symbol, start, end, interval, log_fn)


class FyersConnector:
    """
    Fyers API connector.
    Requires: pip install fyers-apiv3
    API keys from: https://myapi.fyers.in/
    """
    def __init__(self, api_key: str, access_token: str):
        self.client_id = api_key
        self.access_token = normalize_fyers_access_token(api_key, access_token)
        self._fyers = None

    def _connect(self):
        try:
            from fyers_apiv3 import fyersModel
            self._fyers = fyersModel.FyersModel(client_id=self.client_id, is_async=False, token=self.access_token, log_path="")
        except ImportError:
            raise ImportError(
                "fyers-apiv3 not installed.\n"
                "Run: pip install fyers-apiv3"
            )

    def validate(self) -> dict:
        self._connect()
        try:
            profile = self._fyers.get_profile()
            if profile.get('s') == 'ok':
                return {
                    "status": "connected",
                    "broker": "fyers",
                    "user_id": profile.get("data", {}).get("fy_id"),
                    "user_name": profile.get("data", {}).get("name"),
                }
            else:
                return {"status": "error", "broker": "fyers", "error": profile.get("message", "Validation failed")}
        except Exception as e:
            return {"status": "error", "broker": "fyers", "error": str(e)}

    def get_historical(
        self,
        symbol: str,
        start: str,
        end: str,
        interval: str = "1d",
        log_fn: Optional[Callable] = None,
    ) -> pd.DataFrame:
        self._connect()
        
        # Fyers intervals: 1, 5, 15, 30, 60, D, W, M
        interval_map = {
            "1d": "D", "1h": "60", "15m": "15",
            "5m": "5", "1m": "1", "1wk": "W"
        }
        fyers_interval = interval_map.get(interval.lower(), interval)

        if log_fn:
            log_fn(f"[fyers] Fetching {symbol} | {fyers_interval} | {start} → {end}")

        try:
            start_date = datetime.strptime(start, "%Y-%m-%d").strftime("%Y-%m-%d")
            end_date = datetime.strptime(end, "%Y-%m-%d").strftime("%Y-%m-%d")

            data = {
                "symbol": symbol,
                "resolution": fyers_interval,
                "date_format": "1",
                "range_from": start_date,
                "range_to": end_date,
                "cont_flag": "1"
            }

            response = self._fyers.history(data=data)
            
            if response.get("s") != "ok":
                raise ValueError(f"Fyers error: {response.get('message', 'Unknown error')}")

            candles = response.get("candles", [])
            if not candles:
                raise ValueError(f"No data returned from Fyers for {symbol}")

            df = pd.DataFrame(candles, columns=["Date", "open", "high", "low", "close", "volume"])
            df["Date"] = pd.to_datetime(df["Date"], unit="s")
            # Fyers timestamps are in GMT, so we might need to localize if required, but default behavior is fine
            df = df.set_index("Date")
            
            # Remove localization if localized to safely mix with other logic
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            if log_fn:
                log_fn(f"[fyers] Received {len(df)} bars")
            return df

        except Exception as e:
            if log_fn:
                log_fn(f"[fyers] Error: {e}. Falling back to yfinance...")
            from backend.modules.data_ingestion import load_from_yfinance
            return load_from_yfinance(symbol, start, end, interval, log_fn)


def _get_fyers_session_model():
    try:
        from fyers_apiv3 import fyersModel
        return fyersModel.SessionModel
    except ImportError:
        raise ImportError(
            "fyers-apiv3 not installed.\n"
            "Run: pip install fyers-apiv3"
        )


def generate_fyers_auth_url(
    api_key: str,
    app_secret: str,
    redirect_uri: str,
    state: str,
) -> str:
    """Build the FYERS login URL using the official SDK flow."""
    SessionModel = _get_fyers_session_model()
    session = SessionModel(
        client_id=api_key,
        secret_key=app_secret,
        redirect_uri=redirect_uri,
        response_type="code",
        grant_type="authorization_code",
        state=state,
    )
    return session.generate_authcode()


def exchange_fyers_auth_code(
    api_key: str,
    app_secret: str,
    redirect_uri: str,
    auth_code: str,
) -> dict:
    """Exchange FYERS auth_code for an access token using the official SDK flow."""
    SessionModel = _get_fyers_session_model()
    session = SessionModel(
        client_id=api_key,
        secret_key=app_secret,
        redirect_uri=redirect_uri,
        response_type="code",
        grant_type="authorization_code",
    )
    session.set_token(auth_code)
    response = session.generate_token()

    access_token = response.get("access_token")
    if not access_token:
        raise ValueError(response.get("message") or response.get("error") or "Failed to generate FYERS access token")

    return {
        "status": "ok",
        "broker": "fyers",
        "access_token": access_token,
        "refresh_token": response.get("refresh_token"),
    }




def validate_broker(broker: str, api_key: str, secret_key: str, base_url: str = "") -> dict:
    """Unified broker validation."""
    if broker == "alpaca":
        conn = AlpacaConnector(api_key, secret_key, base_url or "https://paper-api.alpaca.markets")
        return conn.validate()
    elif broker == "zerodha":
        conn = ZerodhaConnector(api_key, secret_key)
        return conn.validate()
    elif broker == "fyers":
        conn = FyersConnector(api_key, secret_key)
        return conn.validate()
    else:
        return {"status": "error", "error": f"Unknown broker: {broker}"}
