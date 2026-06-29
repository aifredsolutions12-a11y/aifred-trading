"""
Tool registry the agent can call mid-reasoning.
Each tool is wrapped with @monitor so failures are tracked in api_health.json.
"""
from data_collector.chart_data import fetch_klines, fetch_funding_rate
from data_collector.indicators import compute_indicators, summarize_indicators
from memory.journal import recent_signals
from memory.stats import compute_stats
from utils.api_monitor import monitor


@monitor("tool:cross_tf")
def cross_timeframe_check(symbol: str, timeframe: str) -> dict:
    """Quick TA snapshot on a different timeframe for confirmation."""
    df = fetch_klines(symbol, timeframe, 200)
    return summarize_indicators(compute_indicators(df))


@monitor("tool:past_signals")
def lookup_past_signals(symbol: str, timeframe: str, n: int = 5) -> list:
    """Return the most recent n signals from the journal."""
    return recent_signals(symbol=symbol, timeframe=timeframe, n=n)


@monitor("tool:funding")
def funding_check(symbol: str) -> dict:
    f = fetch_funding_rate(symbol)
    if f is None:
        return {"funding_rate": None, "interpretation": "unavailable"}
    if f > 0.0003:
        interp = "long-heavy (contrarian bearish)"
    elif f < -0.0003:
        interp = "short-heavy (contrarian bullish)"
    else:
        interp = "neutral"
    return {"funding_rate": f, "interpretation": interp}


@monitor("tool:stats")
def regime_stats(symbol: str = None, timeframe: str = None) -> dict:
    return compute_stats(symbol=symbol, timeframe=timeframe)


TOOL_REGISTRY = {
    "cross_timeframe_check": cross_timeframe_check,
    "lookup_past_signals":   lookup_past_signals,
    "funding_check":         funding_check,
    "regime_stats":          regime_stats,
}


def execute_tool(name: str, args: dict):
    if name not in TOOL_REGISTRY:
        return {"error": f"unknown tool '{name}'", "available": list(TOOL_REGISTRY.keys())}
    try:
        return TOOL_REGISTRY[name](**(args or {}))
    except TypeError as e:
        return {"error": f"bad args for {name}: {e}"}
    except Exception as e:
        return {"error": str(e)}
