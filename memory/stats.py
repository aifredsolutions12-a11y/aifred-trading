"""
Aggregate performance statistics from the journal.
v3 — supports new outcome types via win_loss_class.
"""
from collections import defaultdict
from memory.journal import read_journal, classify_outcome


def compute_stats(symbol: str = None, timeframe: str = None) -> dict:
    rows = read_journal()

    # v3: Include all outcomes that classify as WIN / LOSS / BREAK_EVEN
    # NO_TRADE and OPEN are excluded
    def is_closed_trade(r):
        cls = r.get("win_loss_class") or classify_outcome(r.get("outcome"))
        return cls in ("WIN", "LOSS", "BREAK_EVEN", "FLAT")

    rows = [r for r in rows if is_closed_trade(r)]

    if symbol:
        rows = [r for r in rows if r["symbol"] == symbol]
    if timeframe:
        rows = [r for r in rows if r["timeframe"] == timeframe]

    if not rows:
        return {
            "trades": 0, "win_rate": 0, "avg_pnl_pct": 0,
            "by_method": {}, "by_outcome": {},
        }

    # Counts by class
    wins   = sum(1 for r in rows if (r.get("win_loss_class") or classify_outcome(r.get("outcome"))) == "WIN")
    losses = sum(1 for r in rows if (r.get("win_loss_class") or classify_outcome(r.get("outcome"))) == "LOSS")
    flats  = sum(1 for r in rows if (r.get("win_loss_class") or classify_outcome(r.get("outcome"))) in ("BREAK_EVEN", "FLAT"))

    pnl_sum = sum(r.get("pnl_pct", 0) or 0 for r in rows)

    # Outcome breakdown
    by_outcome = defaultdict(int)
    for r in rows:
        by_outcome[r.get("outcome", "?")] += 1

    # Method breakdown
    by_method = defaultdict(lambda: {"n": 0, "wins": 0, "score_sum": 0})
    for r in rows:
        cls = r.get("win_loss_class") or classify_outcome(r.get("outcome"))
        won = cls == "WIN"
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

    total_decisive = wins + losses
    win_rate = round(wins / total_decisive * 100, 1) if total_decisive > 0 else 0

    return {
        "trades": len(rows),
        "wins": wins,
        "losses": losses,
        "flats": flats,
        "win_rate": win_rate,
        "avg_pnl_pct": round(pnl_sum / len(rows), 2),
        "by_method": by_method_out,
        "by_outcome": dict(by_outcome),
    }