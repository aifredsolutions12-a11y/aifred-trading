"""
Agent reset utility — 4 levels of clean slate.

Usage:
  python scripts/reset_agent.py --level soft
  python scripts/reset_agent.py --level medium
  python scripts/reset_agent.py --level hard
  python scripts/reset_agent.py --level nuclear
  python scripts/reset_agent.py --level hard --dry-run
"""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ════════════════════════════════════════════════════════════
# LEVEL: SOFT — Close all open positions
# ════════════════════════════════════════════════════════════
def soft_reset(dry_run=False):
    from memory.journal import read_journal, write_journal
    from data_collector.chart_data import fetch_current_price

    rows = read_journal()
    open_positions = [
        r for r in rows
        if r.get("outcome") is None
        and r.get("position") in ("LONG", "SHORT")
    ]

    print(f"📍 Open positions to close: {len(open_positions)}")
    if not open_positions:
        return 0

    now = datetime.now(timezone.utc).isoformat()
    closed_count = 0

    for r in open_positions:
        symbol = r.get("symbol")
        ez = r.get("entry_zone", {})
        try:
            entry_mid = (float(ez.get("low")) + float(ez.get("high"))) / 2
            current = fetch_current_price(symbol)["price"]
            pnl_pct = (
                (current - entry_mid) / entry_mid * 100
                if r["position"] == "LONG"
                else (entry_mid - current) / entry_mid * 100
            )
            sl = float(r.get("stop_loss_effective") or r.get("stop_loss") or 0)
            risk = abs(entry_mid - sl) if sl else 1
            move = abs(current - entry_mid)
            pnl_R = (move / risk) if r["position"] == "LONG" and current > entry_mid else \
                    -(move / risk) if r["position"] == "LONG" else \
                     (move / risk) if current < entry_mid else \
                    -(move / risk)
        except Exception as e:
            print(f"  ⚠️  {symbol}: price fetch failed → {e}")
            pnl_pct = 0
            pnl_R = 0
            current = None

        if dry_run:
            print(f"  [DRY] Would close {symbol} {r['position']} @ {current} ({pnl_pct:+.2f}%)")
        else:
            r["outcome"] = "MANUAL_CLOSE"
            r["outcome_resolved_at"] = now
            r["outcome_note"] = "Soft reset — closed manually for clean slate"
            r["pnl_pct"] = round(pnl_pct, 2)
            r["pnl_R"] = round(pnl_R, 3)
            r["win_loss_class"] = "WIN" if pnl_pct > 0.5 else "LOSS" if pnl_pct < -0.5 else "FLAT"
            print(f"  ✅ Closed {symbol} {r['position']} @ {current} ({pnl_pct:+.2f}%)")
            closed_count += 1

    if not dry_run:
        write_journal(rows)

    return closed_count


# ════════════════════════════════════════════════════════════
# LEVEL: MEDIUM — Wipe journal, signals, postmortems
# ════════════════════════════════════════════════════════════
def medium_reset(dry_run=False):
    targets = [
        ROOT / "data" / "journal.jsonl",
        ROOT / "data" / "signals",
        ROOT / "data" / "postmortems",
        ROOT / "data" / "agent_state.json",
        ROOT / "data" / "yesterday_summary.json",
    ]
    deleted = 0
    for t in targets:
        if not t.exists():
            continue
        if dry_run:
            print(f"  [DRY] Would delete: {t}")
        else:
            if t.is_dir():
                # Delete contents but keep dir
                for f in t.rglob("*"):
                    if f.is_file():
                        f.unlink()
                        deleted += 1
                print(f"  ✅ Cleared dir: {t}")
            else:
                t.unlink()
                deleted += 1
                print(f"  ✅ Deleted: {t}")
    # Recreate empty journal
    if not dry_run:
        (ROOT / "data" / "journal.jsonl").touch()
        (ROOT / "data" / "signals").mkdir(parents=True, exist_ok=True)
        (ROOT / "data" / "postmortems").mkdir(parents=True, exist_ok=True)
    return deleted


# ════════════════════════════════════════════════════════════
# LEVEL: HARD — Medium + wipe adaptive weights + dashboard cache
# ════════════════════════════════════════════════════════════
def hard_reset(dry_run=False):
    medium_count = medium_reset(dry_run)
    extra = [
        ROOT / "data" / "adaptive_weights",
        ROOT / "docs" / "data",
    ]
    deleted = 0
    for t in extra:
        if not t.exists():
            continue
        if dry_run:
            print(f"  [DRY] Would clear: {t}")
        else:
            for f in t.rglob("*"):
                if f.is_file():
                    f.unlink()
                    deleted += 1
            print(f"  ✅ Cleared: {t}")
    if not dry_run:
        (ROOT / "data" / "adaptive_weights").mkdir(parents=True, exist_ok=True)
        (ROOT / "docs" / "data").mkdir(parents=True, exist_ok=True)
    return medium_count + deleted


# ════════════════════════════════════════════════════════════
# LEVEL: NUCLEAR — Hard + every data/* file (full factory)
# ════════════════════════════════════════════════════════════
def nuclear_reset(dry_run=False):
    hard_count = hard_reset(dry_run)
    extra_files = list((ROOT / "data").rglob("*"))
    deleted = 0
    for t in extra_files:
        if not t.is_file():
            continue
        if dry_run:
            print(f"  [DRY] Would delete: {t}")
        else:
            t.unlink()
            deleted += 1
    return hard_count + deleted


# ════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--level", choices=["soft", "medium", "hard", "nuclear"], required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--confirm", action="store_true",
                   help="Required for non-soft resets")
    args = p.parse_args()

    print("=" * 60)
    print(f"🧹 AGENT RESET — Level: {args.level.upper()}")
    if args.dry_run:
        print("    (DRY RUN — no changes will be made)")
    print("=" * 60)
    print()

    if args.level in ("medium", "hard", "nuclear") and not args.confirm and not args.dry_run:
        print("❌ ABORTED. Add --confirm to proceed with destructive reset.")
        print(f"   python scripts/reset_agent.py --level {args.level} --confirm")
        sys.exit(1)

    fn = {
        "soft":    soft_reset,
        "medium":  medium_reset,
        "hard":    hard_reset,
        "nuclear": nuclear_reset,
    }[args.level]

    count = fn(dry_run=args.dry_run)

    print()
    print("─" * 60)
    print(f"  ✅ Done. Touched {count} item(s).")
    print("─" * 60)