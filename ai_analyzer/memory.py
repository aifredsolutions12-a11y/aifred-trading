"""
Memory layer — feeds past verdicts + outcomes into new analyses.
"""
import json
from pathlib import Path
from typing import List, Dict, Optional

SIGNALS_DIR = Path("data/signals")
JOURNAL_PATH = Path("data/journal/positions.json")
POSTMORTEM_DIR = Path("data/postmortems")


def load_recent_signals(symbol: str, n: int = 3) -> List[dict]:
    """Load the last N signals for a symbol across all timeframes."""
    pattern = f"{symbol}_*.json"
    files = sorted(SIGNALS_DIR.glob(pattern), reverse=True)
    signals = []
    for f in files[:n]:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                sig = json.load(fh)
                sig["_filename"] = f.name
                signals.append(sig)
        except Exception:
            continue
    return signals


def load_closed_trades(symbol: str, limit: int = 30) -> List[dict]:
    """Load closed trades for a symbol from the journal."""
    if not JOURNAL_PATH.exists():
        return []
    try:
        with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
            all_trades = json.load(f)
    except Exception:
        return []

    closed = [
        t for t in all_trades
        if t.get("symbol") == symbol
        and t.get("outcome") in ("TP1", "SL")
    ]
    return closed[-limit:]


def load_recent_postmortems(symbol: str, n: int = 3) -> List[dict]:
    """Load last N AI post-mortems for a symbol."""
    if not POSTMORTEM_DIR.exists():
        return []
    pattern = f"{symbol}_*.json"
    files = sorted(POSTMORTEM_DIR.glob(pattern), reverse=True)
    out = []
    for f in files[:n]:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                out.append(json.load(fh))
        except Exception:
            continue
    return out


def build_memory_block(symbol: str, max_recent: int = 3) -> str:
    """
    Build a compressed memory text block for prompt injection.
    Includes:
    - Last N verdicts with outcomes
    - Recent post-mortem lessons
    - Win/loss streak
    """
    recent = load_recent_signals(symbol, n=max_recent)
    closed = load_closed_trades(symbol, limit=10)
    postmortems = load_recent_postmortems(symbol, n=max_recent)

    lines = [f"═══ MEMORY FOR {symbol} ═══"]

    # Verdict trail
    if recent:
        lines.append("\nRecent verdicts (latest first):")
        for sig in recent:
            ts = sig.get("timestamp", "")[:16]
            pos = sig.get("position", "?")
            conf = sig.get("confidence", "?")
            score = sig.get("final_confluence") or sig.get("confluence_score", "?")
            lines.append(f"  - {ts} | {pos} ({conf}) confluence={score}")
    else:
        lines.append("\nNo recent verdicts yet.")

    # Win/loss summary
    if closed:
        wins = sum(1 for t in closed if t.get("outcome") == "TP1")
        losses = sum(1 for t in closed if t.get("outcome") == "SL")
        total = wins + losses
        wr = (wins / total * 100) if total > 0 else 0
        lines.append(f"\nLast {total} closed: {wins}W / {losses}L (WR {wr:.0f}%)")

        last_outcome = closed[-1].get("outcome")
        last_pnl = closed[-1].get("pnl_pct", 0)
        lines.append(f"  Most recent outcome: {last_outcome} ({last_pnl:+.2f}%)")

    # Post-mortem lessons
    if postmortems:
        lines.append("\nRecent post-mortem lessons:")
        for pm in postmortems:
            lesson = pm.get("lesson", "")[:200]
            ts = pm.get("date", "")[:10]
            lines.append(f"  [{ts}] {lesson}")

    return "\n".join(lines)