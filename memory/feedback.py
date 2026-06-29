"""
Builds a short human-readable feedback block injected into the agent prompt.
"""
from memory.journal import recent_signals
from memory.stats import compute_stats


def build_feedback_block(symbol: str, timeframe: str) -> str:
    recent = [
        r for r in recent_signals(symbol, timeframe, 10)
        if r.get("outcome") in ("TP1", "SL")
    ]
    if not recent:
        return "  (no resolved trades yet — operating in cold-start mode)"

    wins = sum(1 for r in recent if r["outcome"] == "TP1")
    lines = [f"  • Last {len(recent)} resolved: {wins}W-{len(recent) - wins}L"]

    stats = compute_stats(symbol, timeframe)
    if stats["trades"] >= 5:
        weak   = [m for m, p in stats["by_method"].items() if p["win_rate"] < 45]
        strong = [m for m, p in stats["by_method"].items() if p["win_rate"] > 60]
        if weak:
            lines.append(
                f"  • Underperforming methods: {', '.join(weak)} — be skeptical when these drive the score"
            )
        if strong:
            lines.append(
                f"  • Top performers: {', '.join(strong)} — weigh them more in tight calls"
            )

    return "\n".join(lines)
