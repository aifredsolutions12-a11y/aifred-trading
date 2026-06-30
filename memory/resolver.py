"""
Trade resolver — checks each open signal for TP1/SL hit.
v2 — All 5 fixes applied:
  A. TP1 detection only (TP2 ignored per spec)
  B. Smaller TF for same-candle SL/TP ambiguity
  C. Entry-fill validation (no fake stops)
  D. Stale signal expiration
  E. Smart fetch sizing based on signal age
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import pandas as pd

from data_collector.chart_data import fetch_klines
from memory.journal import read_journal, write_journal

# ════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════
RESOLUTION_TF_MAP = {
    "1w":  "4h",
    "1d":  "1h",
    "4h":  "15m",
    "1h":  "5m",
    "30m": "5m",
    "15m": "1m",
}

# Max age before signal expires (in days)
MAX_AGE_DAYS = {
    "15m": 1,
    "30m": 1,
    "1h":  2,
    "4h":  5,
    "1d":  14,
    "1w":  30,
}

# Multi-TF signals (from v4 analyzer) use 4h as resolution base
MULTITF_RESOLUTION = "15m"
MULTITF_MAX_AGE_DAYS = 5


# ════════════════════════════════════════════════════════════
# UTILITIES
# ════════════════════════════════════════════════════════════
def _detect_timeframe(row: dict) -> str:
    """Pull TF from row — handles both old single-TF and new multi-TF formats."""
    if "timeframe" in row and row["timeframe"]:
        return row["timeframe"]
    # New multi-TF signals use the 4h profile as primary
    if "per_tf_details" in row or row.get("_format") == "multitf":
        return "4h"
    return "4h"


def _smart_fetch_size(symbol: str, logged_at: datetime, resolution_tf: str) -> int:
    """
    Fetch only enough candles to cover from logged_at to now.
    Saves API calls and avoids the 500-candle window cap.
    """
    age_hours = (datetime.now(timezone.utc) - logged_at).total_seconds() / 3600

    candles_per_hour = {
        "1m": 60, "3m": 20, "5m": 12,
        "15m": 4, "30m": 2, "1h": 1,
        "2h": 0.5, "4h": 0.25,
        "1d": 1 / 24, "1w": 1 / 168,
    }.get(resolution_tf, 1)

    needed = int(age_hours * candles_per_hour) + 50  # buffer
    return min(max(needed, 100), 1500)


def _entry_filled(row: dict, df: pd.DataFrame) -> tuple[bool, datetime]:
    """
    Step 1: confirm the entry zone was actually reached.
    Without fill confirmation, we shouldn't measure SL/TP.
    """
    ez = row.get("entry_zone", {})
    if not isinstance(ez, dict):
        return False, None

    low = float(ez.get("low", 0))
    high = float(ez.get("high", 0))
    if low <= 0 or high <= 0:
        return False, None

    for _, candle in df.iterrows():
        hi = float(candle["high"])
        lo = float(candle["low"])
        # Entry zone touched if candle overlaps the zone
        if low <= hi and lo <= high:
            return True, candle["timestamp"]

    return False, None


# ════════════════════════════════════════════════════════════
# CORE RESOLVER
# ════════════════════════════════════════════════════════════
def _hit_check(row: dict) -> dict | None:
    """
    Return updated row if outcome resolved, else None.
    Resolves to: TP1 / SL / NO_FILL / EXPIRED / INVALID / NO_TRADE
    """
    # Already resolved → skip
    if row.get("outcome") is not None:
        return None

    # Not a trade entry
    if row.get("position") not in ("LONG", "SHORT"):
        row["outcome"] = "NO_TRADE"
        row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
        return row

    # Required fields missing
    if not row.get("entry_zone") or row.get("stop_loss") is None or row.get("take_profit_1") is None:
        row["outcome"] = "INVALID"
        row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
        return row

    symbol = row.get("symbol")
    tf = _detect_timeframe(row)

    # Step 1: pick resolution TF (smaller for accuracy)
    if "per_tf_details" in row or row.get("_format") == "multitf":
        resolution_tf = MULTITF_RESOLUTION
        max_age_days = MULTITF_MAX_AGE_DAYS
    else:
        resolution_tf = RESOLUTION_TF_MAP.get(tf, "15m")
        max_age_days = MAX_AGE_DAYS.get(tf, 5)

    # Step 2: parse logged_at
    logged_str = row.get("logged_at") or row.get("timestamp")
    if not logged_str:
        row["outcome"] = "INVALID"
        row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
        return row

    try:
        logged = datetime.fromisoformat(logged_str.replace("Z", "+00:00"))
    except Exception:
        row["outcome"] = "INVALID"
        row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
        return row

    # Step 3: expiration check (FIX D)
    age = datetime.now(timezone.utc) - logged
    if age.days > max_age_days:
        row["outcome"] = "EXPIRED"
        row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
        row["expiration_age_days"] = age.days
        return row

    # Step 4: smart fetch (FIX E)
    try:
        limit = _smart_fetch_size(symbol, logged, resolution_tf)
        df = fetch_klines(symbol, resolution_tf, limit)
    except Exception as e:
        print(f"  ⚠️  {symbol} fetch failed: {e}")
        return None

    if df is None or df.empty:
        return None

    df = df[df["timestamp"] >= pd.Timestamp(logged)].reset_index(drop=True)
    if df.empty:
        return None

    # Step 5: validate entry actually filled (FIX C)
    filled, fill_time = _entry_filled(row, df)
    if not filled:
        # Don't resolve yet — entry might still get hit in future
        # But mark NO_FILL if signal has aged past 75% of its lifetime
        age_pct = age.total_seconds() / (max_age_days * 86400)
        if age_pct > 0.75:
            row["outcome"] = "NO_FILL"
            row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
            return row
        return None

    row["entry_filled_at"] = fill_time.isoformat() if hasattr(fill_time, "isoformat") else str(fill_time)

    # Step 6: scan post-fill candles for SL or TP1 (FIX A: TP1 only)
    df_after_fill = df[df["timestamp"] >= pd.Timestamp(fill_time)].reset_index(drop=True)

    ez = row["entry_zone"]
    entry_mid = (float(ez["low"]) + float(ez["high"])) / 2
    sl = float(row["stop_loss"])
    tp1 = float(row["take_profit_1"])
    is_long = row["position"] == "LONG"

    for _, c in df_after_fill.iterrows():
        hi = float(c["high"])
        lo = float(c["low"])

        if is_long:
            hit_sl = lo <= sl
            hit_tp = hi >= tp1
        else:  # SHORT
            hit_sl = hi >= sl
            hit_tp = lo <= tp1

        # FIX B: same-candle ambiguity → conservative (SL wins on same candle)
        if hit_sl and hit_tp:
            row["outcome"] = "SL"
            row["outcome_note"] = "SL + TP1 same candle — conservative resolution"
            row["pnl_pct"] = round(
                ((sl - entry_mid) / entry_mid * 100) if is_long
                else ((entry_mid - sl) / entry_mid * 100),
                2,
            )
            row["resolution_candle"] = c["timestamp"].isoformat()
            row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
            return row

        if hit_sl:
            row["outcome"] = "SL"
            row["pnl_pct"] = round(
                ((sl - entry_mid) / entry_mid * 100) if is_long
                else ((entry_mid - sl) / entry_mid * 100),
                2,
            )
            row["resolution_candle"] = c["timestamp"].isoformat()
            row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
            return row

        if hit_tp:
            row["outcome"] = "TP1"
            row["pnl_pct"] = round(
                ((tp1 - entry_mid) / entry_mid * 100) if is_long
                else ((entry_mid - tp1) / entry_mid * 100),
                2,
            )
            row["resolution_candle"] = c["timestamp"].isoformat()
            row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
            return row

    # Still open
    return None


# ════════════════════════════════════════════════════════════
# BATCH RUNNER
# ════════════════════════════════════════════════════════════
def resolve_all():
    """Walk every journal entry, attempt resolution, save updates, print summary."""
    rows = read_journal()
    if not rows:
        print("✅ Journal empty — nothing to resolve")
        return

    pending = [r for r in rows if r.get("outcome") is None]
    print(f"\n{'='*60}")
    print(f"🔍 RESOLVER v2 — {len(pending)} pending of {len(rows)} total")
    print(f"{'='*60}\n")

    stats = {
        "TP1": 0, "SL": 0, "NO_FILL": 0, "EXPIRED": 0,
        "INVALID": 0, "NO_TRADE": 0, "skipped": 0,
    }
    updated_count = 0

    for r in rows:
        if r.get("outcome") is not None:
            continue

        result = _hit_check(r)
        if result is None:
            stats["skipped"] += 1
            continue

        outcome = result.get("outcome", "?")
        stats[outcome] = stats.get(outcome, 0) + 1
        updated_count += 1

        pnl = result.get("pnl_pct")
        pnl_str = f" ({pnl:+.2f}%)" if isinstance(pnl, (int, float)) else ""
        symbol = result.get("symbol", "?")
        tf = _detect_timeframe(result)
        print(f"  {symbol}/{tf}: {outcome}{pnl_str}")

    write_journal(rows)

    print(f"\n{'─'*60}")
    print(f"📊 RESOLUTION SUMMARY")
    print(f"{'─'*60}")
    print(f"  ✅ Resolved this pass:  {updated_count}")
    for k, v in stats.items():
        if v > 0 and k != "skipped":
            print(f"     {k:10s}: {v}")
    print(f"  ⏭️  Still open:          {stats['skipped']}")

    # Win rate
    closed_total = stats["TP1"] + stats["SL"]
    if closed_total > 0:
        wr = stats["TP1"] / closed_total * 100
        print(f"  🎯 Pass win rate:       {wr:.1f}% ({stats['TP1']}W / {stats['SL']}L)")
    print(f"{'─'*60}\n")


if __name__ == "__main__":
    resolve_all()