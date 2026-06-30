"""
One-time backfill of v3 fields for currently-open positions.

What it does:
  - Walks data/journal.jsonl
  - For each OPEN LONG/SHORT position with no stop_loss_effective field:
      → fetches current OHLCV → computes ATR
      → calls compute_trade_params to enrich
      → writes the new fields back to the row
  - Saves to journal.jsonl
  - Prints a clean summary

Safe to re-run: positions already enriched (have stop_loss_effective) are skipped.
"""
import sys
from pathlib import Path

# Make sure repo root is on sys.path (so we can import as packages)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory.journal import read_journal, write_journal
from ai_analyzer.trade_params import compute_trade_params
from data_collector.chart_data import fetch_klines
from data_collector.indicators import compute_indicators, summarize_indicators


def backfill():
    print("=" * 60)
    print("🔧 V3 BACKFILL — Open positions only")
    print("=" * 60)

    rows = read_journal()
    if not rows:
        print("✅ Journal empty — nothing to backfill")
        return 0

    targets = [
        r for r in rows
        if r.get("outcome") is None
        and r.get("position") in ("LONG", "SHORT")
        and r.get("stop_loss_effective") is None   # not yet v3
    ]

    print(f"📊 Total journal entries:   {len(rows)}")
    print(f"📍 Open positions:          {sum(1 for r in rows if r.get('outcome') is None and r.get('position') in ('LONG', 'SHORT'))}")
    print(f"🎯 Eligible for backfill:   {len(targets)}\n")

    if not targets:
        print("✅ Nothing to backfill — all open positions already have v3 fields.")
        return 0

    backfilled = 0
    failed = 0

    for r in targets:
        symbol = r.get("symbol")
        tf = r.get("timeframe") or "4h"
        confidence = r.get("final_confluence") or r.get("confluence_score") or 40

        print(f"  → {symbol} ({tf}, conf={confidence}) ...", end=" ", flush=True)

        try:
            df = fetch_klines(symbol, tf, 300)
            df_ind = compute_indicators(df)
            snapshot = summarize_indicators(df_ind)
        except Exception as e:
            print(f"❌ fetch failed: {e}")
            failed += 1
            continue

        try:
            compute_trade_params(
                verdict=r,
                symbol=symbol,
                timeframe=tf,
                confidence_score=confidence,
                ta_snapshot=snapshot,
            )
        except Exception as e:
            print(f"❌ compute failed: {e}")
            failed += 1
            continue

        # Mark as backfilled (for transparency)
        r["_backfilled_v3"] = True
        r["_backfill_note"] = "ATR/max_hold/BE computed from current market (not entry-time)"

        print(
            f"✅ ATR={r.get('atr_at_entry'):.4f}, "
            f"effSL={r.get('stop_loss_effective'):.4f}, "
            f"effTP={r.get('take_profit_effective'):.4f}, "
            f"max_hold={r.get('max_hold_hours')}h, "
            f"BE@{r.get('be_trigger_price'):.4f}"
        )
        backfilled += 1

    # Persist
    write_journal(rows)

    print()
    print("─" * 60)
    print("📊 BACKFILL SUMMARY")
    print("─" * 60)
    print(f"  ✅ Backfilled:  {backfilled}")
    print(f"  ❌ Failed:      {failed}")
    print(f"  ⏭️  Skipped:    {len(rows) - len(targets)} (closed or already v3)")
    print("─" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = backfill()
    sys.exit(exit_code)