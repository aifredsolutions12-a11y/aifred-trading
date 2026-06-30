"""Export latest signals + postmortems + weights + position status to docs/data/ for GitHub Pages.
v3 — adds ATR, BE, time-progress, 3-layer SL/TP fields.
"""
import json
from pathlib import Path
from datetime import datetime, timezone

DOCS_DATA = Path("docs/data")
DOCS_DATA.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════════════════════
# SIGNALS
# ════════════════════════════════════════════════════════════
def export_signals():
    """Read all *_latest.json files → flat list."""
    signals_dir = Path("data/signals")
    if not signals_dir.exists():
        return
    out = []
    for f in sorted(signals_dir.glob("*_latest.json")):
        try:
            sig = json.loads(f.read_text(encoding="utf-8"))
            out.append(sig)
        except Exception as e:
            print(f"⚠️ Could not read {f.name}: {e}")
            continue

    out.sort(key=lambda s: s.get("symbol", ""))
    (DOCS_DATA / "signals_index.json").write_text(
        json.dumps(out, indent=2, default=str)
    )
    print(f"✅ Exported {len(out)} latest signals")


# ════════════════════════════════════════════════════════════
# POSITION STATUS — v3 with ATR/BE/time-progress fields
# ════════════════════════════════════════════════════════════
def export_position_status():
    """Open positions + computed live fields (hours_remaining, time_progress_pct)."""
    journal_path = Path("data/journal.jsonl")
    if not journal_path.exists():
        return
    try:
        with open(journal_path, "r", encoding="utf-8") as f:
            content = f.read()
        if content.strip().startswith("["):
            journal = json.loads(content)
        else:
            journal = [json.loads(line) for line in content.splitlines() if line.strip()]
    except Exception as e:
        print(f"⚠️ Could not read journal: {e}")
        return

    open_positions = [
        t for t in journal
        if t.get("outcome") is None
        and t.get("position") in ("LONG", "SHORT")
    ]

    now = datetime.now(timezone.utc)
    status_list = []
    for p in open_positions:
        # Compute live time-based fields
        hours_remaining = None
        time_progress_pct = None
        age_hours = None
        try:
            logged = datetime.fromisoformat(
                (p.get("logged_at") or "").replace("Z", "+00:00")
            )
            age_seconds = (now - logged).total_seconds()
            age_hours = round(age_seconds / 3600, 1)
            max_hold = float(p.get("max_hold_hours") or 24)
            if max_hold > 0:
                time_progress_pct = round(min(100, age_hours / max_hold * 100), 1)
                hours_remaining = round(max(0, max_hold - age_hours), 1)
        except Exception:
            pass

        status_list.append({
            # Existing
            "symbol":           p.get("symbol"),
            "position":         p.get("position"),
            "confidence":       p.get("confidence"),
            "entry_zone":       p.get("entry_zone"),
            "stop_loss":        p.get("stop_loss"),
            "take_profit_1":    p.get("take_profit_1"),
            "logged_at":        p.get("logged_at"),
            "refresh_count":    p.get("_refresh_count", 0),
            "last_refresh_at":  p.get("_last_refresh_at"),
            "latest_confluence": p.get("_latest_confluence"),
            "latest_confidence": p.get("_latest_confidence"),
            "latest_ev_R":      p.get("_latest_ev_R"),
            "original_confluence": p.get("final_confluence"),

            # v3 — Three-layer SL/TP
            "stop_loss_ai":         p.get("stop_loss_ai"),
            "stop_loss_atr":        p.get("stop_loss_atr"),
            "stop_loss_effective":  p.get("stop_loss_effective"),
            "take_profit_ai":       p.get("take_profit_ai"),
            "take_profit_atr":      p.get("take_profit_atr"),
            "take_profit_effective": p.get("take_profit_effective"),

            # v3 — ATR snapshot
            "atr_at_entry": p.get("atr_at_entry"),
            "atr_pct":      p.get("atr_pct"),
            "atr_tf":       p.get("atr_tf"),

            # v3 — BE tracking
            "be_trigger_price": p.get("be_trigger_price"),
            "be_activated":     p.get("be_activated", False),
            "be_activated_at":  p.get("be_activated_at"),

            # v3 — Time tracking (live-computed)
            "max_hold_hours":     p.get("max_hold_hours"),
            "age_hours":          age_hours,
            "hours_remaining":    hours_remaining,
            "time_progress_pct":  time_progress_pct,
        })

    # Sort by most at-risk first (highest time progress, then BE armed)
    status_list.sort(
        key=lambda s: (-(s.get("time_progress_pct") or 0),
                       not s.get("be_activated", False)),
    )

    (DOCS_DATA / "position_status.json").write_text(
        json.dumps(status_list, indent=2, default=str)
    )
    print(f"✅ Exported {len(status_list)} open positions (with v3 fields)")


# ════════════════════════════════════════════════════════════
# POSTMORTEMS
# ════════════════════════════════════════════════════════════
def export_postmortems():
    pm_dir = Path("data/postmortems")
    if not pm_dir.exists():
        return
    pms = []
    for f in sorted(pm_dir.glob("*.json"), reverse=True):
        try:
            pms.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    by_coin = {}
    for pm in pms:
        coin = pm.get("coin")
        if coin and coin not in by_coin:
            by_coin[coin] = pm
    out = sorted(by_coin.values(), key=lambda p: p.get("coin", ""))
    (DOCS_DATA / "postmortems_index.json").write_text(
        json.dumps(out, indent=2)
    )
    print(f"✅ Exported {len(out)} post-mortems")


# ════════════════════════════════════════════════════════════
# WEIGHTS
# ════════════════════════════════════════════════════════════
def export_weights():
    w_dir = Path("data/adaptive_weights")
    if not w_dir.exists():
        return
    out = []
    for f in sorted(w_dir.glob("*_weights.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    (DOCS_DATA / "weights_index.json").write_text(json.dumps(out, indent=2))
    print(f"✅ Exported {len(out)} weight files")


# ════════════════════════════════════════════════════════════
# v3 NEW: STATS EXTENDED — outcome breakdown by class
# ════════════════════════════════════════════════════════════
def export_stats_extended():
    """Aggregate outcome distribution + tier-based win rates."""
    journal_path = Path("data/journal.jsonl")
    if not journal_path.exists():
        return

    try:
        with open(journal_path, "r", encoding="utf-8") as f:
            content = f.read()
        journal = [json.loads(line) for line in content.splitlines() if line.strip()]
    except Exception:
        return

    # Outcome distribution
    outcome_dist = {}
    for t in journal:
        outcome = t.get("outcome")
        if outcome:
            outcome_dist[outcome] = outcome_dist.get(outcome, 0) + 1

    # Class distribution (WIN/LOSS/BREAK_EVEN/FLAT/NO_TRADE/OPEN)
    class_dist = {}
    for t in journal:
        cls = t.get("win_loss_class")
        if cls is None:
            cls = "OPEN" if t.get("outcome") is None else "LEGACY"
        class_dist[cls] = class_dist.get(cls, 0) + 1

    # BE activation rate (out of closed trades)
    closed = [t for t in journal if t.get("outcome") is not None]
    be_activated_count = sum(1 for t in closed if t.get("be_activated"))
    be_activation_rate = (
        round(be_activated_count / len(closed) * 100, 1) if closed else 0
    )

    # Average P&L by outcome class
    pnl_by_class = {}
    for t in journal:
        cls = t.get("win_loss_class")
        pnl = t.get("pnl_pct")
        if cls and pnl is not None:
            pnl_by_class.setdefault(cls, []).append(pnl)
    avg_pnl_by_class = {
        k: round(sum(v) / len(v), 2) for k, v in pnl_by_class.items() if v
    }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "outcome_distribution": outcome_dist,
        "class_distribution": class_dist,
        "be_activation_rate_pct": be_activation_rate,
        "be_activated_count": be_activated_count,
        "closed_trades_total": len(closed),
        "avg_pnl_by_class": avg_pnl_by_class,
    }

    (DOCS_DATA / "stats_extended.json").write_text(
        json.dumps(payload, indent=2, default=str)
    )
    print(f"✅ Exported stats_extended (v3): {sum(outcome_dist.values())} outcomes tracked")


if __name__ == "__main__":
    export_signals()
    export_position_status()
    export_postmortems()
    export_weights()
    export_stats_extended()