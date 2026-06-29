"""
On-chain / derivatives metrics from CoinGecko + Binance Futures.
"""
import requests

COINGECKO_GLOBAL = "https://api.coingecko.com/api/v3/global"
BINANCE_FUT      = "https://fapi.binance.com/fapi/v1"
BINANCE_FUT_DATA = "https://fapi.binance.com/futures/data"


def fetch_btc_dominance() -> dict:
    try:
        r = requests.get(COINGECKO_GLOBAL, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", {})
        mcap = data.get("market_cap_percentage", {})
        return {
            "btc_dominance_pct": round(mcap.get("btc", 0), 2),
            "eth_dominance_pct": round(mcap.get("eth", 0), 2),
            "total_market_cap_usd": data.get("total_market_cap", {}).get("usd"),
            "market_cap_change_24h_pct": round(data.get("market_cap_change_percentage_24h_usd", 0), 2),
        }
    except Exception as e:
        return {"error": str(e), "btc_dominance_pct": None}


def fetch_open_interest(symbol: str = "BTCUSDT") -> dict:
    try:
        r = requests.get(f"{BINANCE_FUT}/openInterest", params={"symbol": symbol}, timeout=10)
        r.raise_for_status()
        d = r.json()
        return {"symbol": symbol, "open_interest": float(d.get("openInterest", 0)), "time": d.get("time")}
    except Exception as e:
        return {"symbol": symbol, "error": str(e), "open_interest": None}


def fetch_long_short_ratio(symbol: str = "BTCUSDT") -> dict:
    """Top-trader long/short account ratio (1h period, latest sample)."""
    try:
        r = requests.get(f"{BINANCE_FUT_DATA}/topLongShortAccountRatio",
                         params={"symbol": symbol, "period": "1h", "limit": 1}, timeout=10)
        r.raise_for_status()
        data = r.json()
        if not data:
            return {"symbol": symbol, "long_short_ratio": None}
        latest = data[0]
        return {
            "symbol": symbol,
            "long_short_ratio": float(latest.get("longShortRatio", 0)),
            "long_account_pct": float(latest.get("longAccount", 0)) * 100,
            "short_account_pct": float(latest.get("shortAccount", 0)) * 100,
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e), "long_short_ratio": None}


def fetch_onchain_snapshot(symbol: str = "BTCUSDT") -> dict:
    return {
        "dominance": fetch_btc_dominance(),
        "open_interest": fetch_open_interest(symbol),
        "long_short": fetch_long_short_ratio(symbol),
    }
