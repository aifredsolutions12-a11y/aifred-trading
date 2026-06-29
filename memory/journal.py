"""
Append-only signal log + read/write/filter helpers.
"""
import json
from pathlib import Path
from datetime import datetime, timezone

JOURNAL = Path("data/journal.jsonl")
JOURNAL.parent.mkdir(parents=True, exist_ok=True)


def log_signal(verdict: dict):
    """Append a new signal verdict to the journal."""
    entry = {
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "symbol": verdict.get("symbol"),
        "timeframe": verdict.get("timeframe"),
        "position": verdict.get("position"),
        "confidence": verdict.get("confidence"),
        "confluence_score": verdict.get("confluence_score"),
        "entry_zone": verdict.get("entry_zone"),
        "stop_loss": verdict.get("stop_loss"),
        "take_profit_1": verdict.get("take_profit_1"),
        "take_profit_2": verdict.get("take_profit_2"),
        "method_scores": verdict.get("method_scores"),
        "agent_meta": verdict.get("agent_meta"),
        "outcome": None,
        "outcome_resolved_at": None,
        "pnl_pct": None,
    }
    with open(JOURNAL, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def read_journal() -> list:
    if not JOURNAL.exists():
        return []
    rows = []
    for line in JOURNAL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def write_journal(entries: list):
    with open(JOURNAL, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, default=str) + "\n")


def recent_signals(symbol: str = None, timeframe: str = None, n: int = 10) -> list:
    rows = read_journal()
    if symbol:
        rows = [r for r in rows if r.get("symbol") == symbol]
    if timeframe:
        rows = [r for r in rows if r.get("timeframe") == timeframe]
    return rows[-n:]
