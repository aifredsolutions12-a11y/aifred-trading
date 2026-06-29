"""
Binance OHLCV fetcher with spot/futures auto-fallback.
"""
import requests
import pandas as pd
from datetime import datetime, timezone

SPOT_BASE = "https://data-api.binance.vision/api/v3"
FUTURES_BASE = "https://fapi.binance.com/fapi/v1"

VALID_BINANCE_INTERVALS = {
    "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h",
    "6h", "8h", "12h", "1d", "3d", "1w", "1M"
}


def validate_interval(interval: str) -> str:
    if interval not in VALID_BINANCE_INTERVALS:
        raise ValueError(f"Invalid interval '{interval}'. Valid: {sorted(VALID_BINANCE_INTERVALS)}")
    return interval


def _get_base_url(source: str) -> str:
    return FUTURES_BASE if source == "futures" else SPOT_BASE


def _request_binance(endpoint: str, params: dict, source: str = "spot") -> dict | list:
    """Request with auto-fallback from spot to futures on certain errors."""
    base = _get_base_url(source)
    url = f"{base}/{endpoint}"
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 400 and source == "spot":
            # try futures
            r = requests.get(f"{FUTURES_BASE}/{endpoint}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise RuntimeError(f"Binance request failed ({endpoint}): {e}")


def fetch_klines(symbol: str, interval: str, limit: int = 200, source: str = "spot") -> pd.DataFrame:
    """Return OHLCV DataFrame with timestamp, open, high, low, close, volume columns."""
    validate_interval(interval)
    data = _request_binance("klines",
                            {"symbol": symbol.upper(), "interval": interval, "limit": int(limit)},
                            source=source)
    if not data:
        raise RuntimeError(f"No kline data returned for {symbol} {interval}")
    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "qav", "trades", "tbbav", "tbqav", "ignore"
    ])
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])
    return df[["timestamp", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def fetch_current_price(symbol: str, source: str = "spot") -> dict:
    """Fetch latest ticker stats."""
    data = _request_binance("ticker/24hr", {"symbol": symbol.upper()}, source=source)
    return {
        "symbol": symbol.upper(),
        "price": float(data.get("lastPrice", 0)),
        "change_24h_pct": float(data.get("priceChangePercent", 0)),
        "volume_24h": float(data.get("volume", 0)),
        "high_24h": float(data.get("highPrice", 0)),
        "low_24h": float(data.get("lowPrice", 0)),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
    }


def fetch_funding_rate(symbol: str) -> float | None:
    """Futures-only funding rate. Returns None if unavailable."""
    try:
        url = f"{FUTURES_BASE}/premiumIndex"
        r = requests.get(url, params={"symbol": symbol.upper()}, timeout=10)
        r.raise_for_status()
        return float(r.json().get("lastFundingRate", 0))
    except Exception:
        return None


def fetch_symbol_bundle(symbol: str, interval: str, limit: int = 200) -> dict:
    """Get klines + ticker + funding in one call."""
    return {
        "klines": fetch_klines(symbol, interval, limit),
        "ticker": fetch_current_price(symbol),
        "funding_rate": fetch_funding_rate(symbol),
    }
