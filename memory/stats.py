"""
Aggregate performance statistics from the journal.
"""
from collections import defaultdict
from memory.journal import read_journal


def compute_stats(symbol: str = None, timeframe: str = None) -> dict:
    rows = [r for r in read_journal() if r.get("outcome") in ("TP1", "SL")]
    if symbol:
        rows = [r for r in rows if r["symbol"] == symbol]
    if timeframe:
        rows = [r for r in rows if r["timeframe"] == timeframe]

    if not rows:
        return {"trades": 0, "win_rate": 0, "avg_pnl_pct": 0, "by_method": {}}

    wins = sum(1 for r in rows if r["outcome"] == "TP1")
    pnl_sum = sum(r.get("pnl_pct", 0) or 0 for r in rows)

    by_method = defaultdict(lambda: {"n": 0, "wins": 0, "score_sum": 0})
    for r in rows:
        won = r["outcome"] == "TP1"
        for m, s in (r.get("method_scores") or {}).items():
            by_method[m]["n"] += 1
            by_method[m]["wins"] += int(won)
            by_method[m]["score_sum"] += s or 0

    by_method_out = {}
    for m, v in by_method.items():
        if v["n"] == 0:
            continue
        by_method_out[m] = {
            "win_rate": round(v["wins"] / v["n"] * 100, 1),
            "avg_score": round(v["score_sum"] / v["n"], 1),
            "n": v["n"],
        }

    return {
        "trades": len(rows),
        "win_rate": round(wins / len(rows) * 100, 1),
        "avg_pnl_pct": round(pnl_sum / len(rows), 2),
        "by_method": by_method_out,
    }
