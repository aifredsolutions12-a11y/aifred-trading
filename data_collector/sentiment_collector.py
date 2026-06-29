"""
Fear & Greed Index collector.
"""
import requests
from datetime import datetime, timezone

FNG_URL = "https://api.alternative.me/fng/"


def fetch_fear_greed(days: int = 7) -> dict:
    """Fetch F&G index history."""
    try:
        r = requests.get(FNG_URL, params={"limit": days}, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])
    except Exception as e:
        return {"error": str(e), "current_value": 50, "current_label": "Neutral",
                "trend_7d": "stable", "delta_7d": 0, "history": [], "contrarian_signal": "neutral"}

    history = []
    for d in data:
        history.append({
            "date": datetime.fromtimestamp(int(d["timestamp"]), tz=timezone.utc).strftime("%Y-%m-%d"),
            "value": int(d["value"]),
            "label": d["value_classification"],
        })

    if not history:
        return {"current_value": 50, "current_label": "Neutral", "trend_7d": "stable",
                "delta_7d": 0, "history": [], "contrarian_signal": "neutral"}

    current = history[0]
    oldest  = history[-1]
    delta = current["value"] - oldest["value"]
    trend = "rising" if delta > 5 else "falling" if delta < -5 else "stable"

    if current["value"] <= 20:
        contrarian = "buy"
    elif current["value"] >= 80:
        contrarian = "sell"
    else:
        contrarian = "neutral"

    return {
        "current_value": current["value"],
        "current_label": current["label"],
        "trend_7d": trend,
        "delta_7d": delta,
        "history": history,
        "contrarian_signal": contrarian,
    }
