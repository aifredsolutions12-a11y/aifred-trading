"""
Wraps every external API call to track success/failure, latency, and last error.
Writes data/api_health.json which the dashboard reads.
"""
import json
import time
from pathlib import Path
from functools import wraps
from datetime import datetime, timezone

HEALTH_PATH = Path("data/api_health.json")
HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
MAX_EVENTS = 200


def _load():
    if HEALTH_PATH.exists():
        try:
            return json.loads(HEALTH_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"providers": {}, "events": []}


def _save(d):
    d["events"] = d["events"][-MAX_EVENTS:]
    HEALTH_PATH.write_text(json.dumps(d, indent=2, default=str), encoding="utf-8")


def monitor(provider: str):
    """Decorator: tracks a single provider's call health."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.time()
            err = None
            ok = True
            result = None
            try:
                result = fn(*args, **kwargs)
            except Exception as e:
                ok = False
                err = f"{type(e).__name__}: {e}"
            latency_ms = int((time.time() - t0) * 1000)

            d = _load()
            p = d["providers"].setdefault(
                provider,
                {"calls": 0, "errors": 0, "last_error": None, "avg_latency_ms": 0},
            )
            p["calls"] += 1
            p["avg_latency_ms"] = int(
                (p["avg_latency_ms"] * (p["calls"] - 1) + latency_ms) / p["calls"]
            )
            if not ok:
                p["errors"] += 1
                p["last_error"] = err
            p["error_rate_pct"] = round(p["errors"] / p["calls"] * 100, 2)

            if p["error_rate_pct"] < 5:
                p["status"] = "🟢"   # 🟢
            elif p["error_rate_pct"] < 20:
                p["status"] = "🟡"   # 🟡
            else:
                p["status"] = "🔴"   # 🔴

            d["events"].append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "provider": provider,
                "ok": ok,
                "latency_ms": latency_ms,
                "error": err,
            })
            _save(d)

            if not ok:
                raise RuntimeError(err)
            return result
        return wrapper
    return deco
