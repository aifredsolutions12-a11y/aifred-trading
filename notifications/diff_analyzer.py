"""
Detects what changed between runs.
Used by hourly update to compare current state vs last run's state.
"""
import json
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime, timezone

STATE_FILE = Path("data/agent_state.json")


def load_previous_state() -> Dict:
    """Load the state from the previous agent run."""
    if not STATE_FILE.exists():
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_current_state(state: Dict) -> None:
    """Persist the current run's state for next run's comparison."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)


def build_state_from_signals(signals: List[Dict]) -> Dict:
    """
    Reduce each signal to its key state for comparison.
    """
    state = {}
    for s in signals:
        sym = s.get("symbol")
        if not sym:
            continue
        state[sym] = {
            "position": s.get("position"),
            "confidence": s.get("confidence"),
            "final_confluence": s.get("final_confluence"),
            "ev_R": s.get("ev_R"),
            "timestamp": s.get("timestamp"),
        }
    return state


def compare_states(prev: Dict, curr: Dict) -> Dict:
    """
    Compare two state dicts and return categorized changes:
      - unchanged: same position, same confidence
      - attention: same position but conviction/EV dropped significantly
      - flipped: position direction changed
      - new_opens: new actionable position (was WAIT, now LONG/SHORT)
      - closed: position no longer in current state
    """
    result = {
        "unchanged": [],
        "attention": [],
        "flipped": [],
        "new_opens": [],
        "closed": [],
    }

    all_symbols = set(prev.keys()) | set(curr.keys())

    for sym in all_symbols:
        old = prev.get(sym)
        new = curr.get(sym)

        # Coin missing from current → was removed (rare)
        if not new:
            continue

        # New coin (no previous state)
        if not old:
            if new.get("position") in ("LONG", "SHORT"):
                result["new_opens"].append({"symbol": sym, **new})
            continue

        old_pos = old.get("position")
        new_pos = new.get("position")

        # Direction flipped
        if old_pos in ("LONG", "SHORT") and new_pos in ("LONG", "SHORT") and old_pos != new_pos:
            result["flipped"].append({
                "symbol": sym,
                "old_direction": old_pos,
                "new_direction": new_pos,
                "old_confidence": old.get("confidence"),
                "new_confidence": new.get("confidence"),
            })
            continue

        # Was waiting, now actionable
        if old_pos not in ("LONG", "SHORT") and new_pos in ("LONG", "SHORT"):
            result["new_opens"].append({"symbol": sym, **new})
            continue

        # Was active, now waiting (AI says wait but position should still be open)
        if old_pos in ("LONG", "SHORT") and new_pos not in ("LONG", "SHORT"):
            result["attention"].append({
                "symbol": sym,
                "reason": "AI now says WAIT",
                "old": f"{old_pos} ({old.get('confidence')})",
                "new": f"{new_pos}",
                "suggestion": "Consider closing or wait for resolver",
            })
            continue

        # Same direction — check for attention triggers
        if old_pos == new_pos and new_pos in ("LONG", "SHORT"):
            old_conf = old.get("confidence")
            new_conf = new.get("confidence")
            old_conv = old.get("final_confluence", 50)
            new_conv = new.get("final_confluence", 50)
            old_ev = old.get("ev_R", 0)
            new_ev = new.get("ev_R", 0)

            attention_triggered = False
            attention_reasons = []

            # Confidence downgrade
            conf_ranks = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "SKIP": 0}
            if conf_ranks.get(new_conf, 0) < conf_ranks.get(old_conf, 0):
                attention_triggered = True
                attention_reasons.append(f"Confidence: {old_conf}→{new_conf}")

            # Confluence drop > 10
            if old_conv and new_conv and (old_conv - new_conv) > 10:
                attention_triggered = True
                attention_reasons.append(f"Confluence: {old_conv:.0f}→{new_conv:.0f}")

            # EV turned negative
            if old_ev > 0 and new_ev < 0:
                attention_triggered = True
                attention_reasons.append(f"EV: {old_ev:+.2f}→{new_ev:+.2f}R")

            if attention_triggered:
                result["attention"].append({
                    "symbol": sym,
                    "reason": " │ ".join(attention_reasons),
                    "old": f"{old_pos} ({old_conf})",
                    "new": f"{new_pos} ({new_conf})",
                    "suggestion": "Consider tightening stop or reducing size",
                })
            else:
                result["unchanged"].append({
                    "symbol": sym,
                    **new,
                })

    return result