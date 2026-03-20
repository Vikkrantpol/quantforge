import os
from dotenv import load_dotenv, dotenv_values

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")

def reload_settings():
    file_values = dotenv_values(ENV_FILE) if os.path.exists(ENV_FILE) else {}
    current_values = {
        "HOST": globals().get("HOST", "127.0.0.1"),
        "PORT": str(globals().get("PORT", "8010")),
        "FRONTEND_URL": globals().get("FRONTEND_URL", "http://localhost:5173"),
        "ALPACA_API_KEY": globals().get("ALPACA_API_KEY", ""),
        "ALPACA_SECRET_KEY": globals().get("ALPACA_SECRET_KEY", ""),
        "ALPACA_BASE_URL": globals().get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"),
        "KITE_API_KEY": globals().get("KITE_API_KEY", ""),
        "KITE_ACCESS_TOKEN": globals().get("KITE_ACCESS_TOKEN", ""),
        "FYERS_APP_ID": globals().get("FYERS_APP_ID", ""),
        "FYERS_SECRET_KEY": globals().get("FYERS_SECRET_KEY", ""),
        "FYERS_REDIRECT_URI": globals().get("FYERS_REDIRECT_URI", "http://localhost:5173/broker/fyers/callback"),
        "FYERS_ACCESS_TOKEN": globals().get("FYERS_ACCESS_TOKEN", ""),
    }

    def read(key: str, default: str = "") -> str:
        if key in file_values and file_values[key] is not None:
            return str(file_values[key])
        if key in os.environ:
            return os.environ[key]
        return str(current_values.get(key, default))

    global HOST, PORT, FRONTEND_URL
    global ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL
    global KITE_API_KEY, KITE_ACCESS_TOKEN
    global FYERS_APP_ID, FYERS_SECRET_KEY, FYERS_REDIRECT_URI, FYERS_ACCESS_TOKEN

    HOST = read("HOST", "127.0.0.1")
    PORT = int(read("PORT", "8010"))
    FRONTEND_URL = read("FRONTEND_URL", "http://localhost:5173")

    ALPACA_API_KEY = read("ALPACA_API_KEY", "")
    ALPACA_SECRET_KEY = read("ALPACA_SECRET_KEY", "")
    ALPACA_BASE_URL = read("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    KITE_API_KEY = read("KITE_API_KEY", "")
    KITE_ACCESS_TOKEN = read("KITE_ACCESS_TOKEN", "")

    FYERS_APP_ID = read("FYERS_APP_ID", "")
    FYERS_SECRET_KEY = read("FYERS_SECRET_KEY", "")
    FYERS_REDIRECT_URI = read("FYERS_REDIRECT_URI", f"{FRONTEND_URL}/broker/fyers/callback")
    FYERS_ACCESS_TOKEN = read("FYERS_ACCESS_TOKEN", "")

    return {
        "HOST": HOST,
        "PORT": PORT,
        "FRONTEND_URL": FRONTEND_URL,
        "FYERS_REDIRECT_URI": FYERS_REDIRECT_URI,
    }


load_dotenv(ENV_FILE)
reload_settings()

# Server
HOST = HOST
PORT = PORT
FRONTEND_URL = FRONTEND_URL

# Alpaca broker (optional)
ALPACA_API_KEY = ALPACA_API_KEY
ALPACA_SECRET_KEY = ALPACA_SECRET_KEY
ALPACA_BASE_URL = ALPACA_BASE_URL

# Zerodha / Kite (optional)
KITE_API_KEY = KITE_API_KEY
KITE_ACCESS_TOKEN = KITE_ACCESS_TOKEN

# FYERS (optional)
FYERS_APP_ID = FYERS_APP_ID
FYERS_SECRET_KEY = FYERS_SECRET_KEY
FYERS_REDIRECT_URI = FYERS_REDIRECT_URI
FYERS_ACCESS_TOKEN = FYERS_ACCESS_TOKEN

# Data directory
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Temp directory for downloads
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
os.makedirs(TEMP_DIR, exist_ok=True)
