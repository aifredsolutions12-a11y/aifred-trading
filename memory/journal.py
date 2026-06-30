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


from datetime import datetime, timezone


def find_open_position(journal: list, symbol: str) -> dict | None:
    """Return the most recent OPEN position for a symbol, or None."""
    open_positions = [
        t for t in journal
        if t.get("symbol") == symbol
        and t.get("outcome") is None
        and t.get("position") in ("LONG", "SHORT")
    ]
    if not open_positions:
        return None
    # Most recent open position
    return sorted(
        open_positions,
        key=lambda t: t.get("logged_at", ""),
        reverse=True,
    )[0]


def close_position_as_flipped(position: dict, new_direction: str) -> None:
    """Mark a position as closed due to direction flip. Modifies dict in place."""
    position["outcome"] = "FLIPPED"
    position["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
    position["outcome_note"] = (
        f"Direction changed: {position.get('position')} → {new_direction}"
    )


def update_position_refresh(position: dict, verdict: dict) -> None:
    """Update an open position's refresh metadata. Modifies dict in place."""
    now = datetime.now(timezone.utc).isoformat()
    position["_last_refresh_at"] = now
    position["_refresh_count"] = position.get("_refresh_count", 0) + 1
    position["_latest_confluence"] = verdict.get("final_confluence")
    position["_latest_confidence"] = verdict.get("confidence")
    position["_latest_ev_R"] = verdict.get("ev_R")
    position["_latest_win_prob"] = verdict.get("estimated_win_prob_pct")


def append_new_position(journal: list, verdict: dict, signal_filename: str) -> dict:
    """Add a brand new trade entry to the journal."""
    entry = {
        **verdict,
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "_signal_file": signal_filename,
        "_refresh_count": 0,
    }
    journal.append(entry)
    return entry
