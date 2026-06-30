"""
Trade resolver v3 — checks each open signal for TP/SL/BE/TIME-OUT.

v3 additions on top of v2:
  F. Break-even (BE) tracking — auto-arm at 50% of effective TP distance
  G. Time-based force close — max_hold_hours triggers TIME_WIN/LOSS/FLAT
  H. Uses stop_loss_effective / take_profit_effective (v3 fields, fallback to v2)
  I. Tags every outcome with win_loss_class for clean stats

v2 features preserved unchanged:
  A. TP1 detection only (TP2 ignored per spec)
  B. Smaller TF for same-candle SL/TP ambiguity
  C. Entry-fill validation
  D. Stale signal expiration
  E. Smart fetch sizing
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import pandas as pd

from data_collector.chart_data import fetch_klines
from memory.journal import read_journal, write_journal, classify_outcome

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

MAX_AGE_DAYS = {
    "15m": 1,
    "30m": 1,
    "1h":  2,
    "4h":  5,
    "1d":  14,
    "1w":  30,
}

MULTITF_RESOLUTION = "15m"
MULTITF_MAX_AGE_DAYS = 5

# v3: Time-out R-thresholds (tiered classification)
TIME_WIN_R_THRESHOLD  = 0.5    # P&L >= +0.5R → TIME_WIN
TIME_LOSS_R_THRESHOLD = -0.5   # P&L <= -0.5R → TIME_LOSS
# Everything between → TIME_FLAT

# v3: Default max hold if missing in legacy entries
DEFAULT_MAX_HOLD_HOURS = 24


# ════════════════════════════════════════════════════════════
# UTILITIES (v2 — unchanged)
# ════════════════════════════════════════════════════════════
def _detect_timeframe(row: dict) -> str:
    if "timeframe" in row and row["timeframe"]:
        return row["timeframe"]
    if "per_tf_details" in row or row.get("_format") == "multitf":
        return "4h"
    return "4h"


def _smart_fetch_size(symbol: str, logged_at: datetime, resolution_tf: str) -> int:
    age_hours = (datetime.now(timezone.utc) - logged_at).total_seconds() / 3600
    candles_per_hour = {
        "1m": 60, "3m": 20, "5m": 12,
        "15m": 4, "30m": 2, "1h": 1,
        "2h": 0.5, "4h": 0.25,
        "1d": 1 / 24, "1w": 1 / 168,
    }.get(resolution_tf, 1)
    needed = int(age_hours * candles_per_hour) + 50
    return min(max(needed, 100), 1500)


def _entry_filled(row: dict, df: pd.DataFrame) -> tuple:
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
        if low <= hi and lo <= high:
            return True, candle["timestamp"]
    return False, None


# ════════════════════════════════════════════════════════════
# v3 HELPERS — Effective SL/TP, BE, Time-out
# ════════════════════════════════════════════════════════════
def _get_effective_sl_tp(row: dict) -> tuple:
    """
    Return (sl, tp) using v3 effective levels with v2 fallback.
    Priority:
      1. stop_loss_effective / take_profit_effective (v3 blended)
      2. stop_loss / take_profit_1 (legacy)
    """
    sl = row.get("stop_loss_effective") or row.get("stop_loss")
    tp = row.get("take_profit_effective") or row.get("take_profit_1")
    if sl is None or tp is None:
        return None, None
    return float(sl), float(tp)


def _compute_be_trigger(entry_mid: float, sl: float, tp: float,
                        is_long: bool, row: dict) -> float:
    """
    Return BE trigger price at 50% of distance from entry to effective TP.
    Uses stored be_trigger_price if already set (from analyzer),
    otherwise computes on the fly.
    """
    stored = row.get("be_trigger_price")
    if stored is not None:
        try:
            return float(stored)
        except (TypeError, ValueError):
            pass

    if is_long:
        return entry_mid + (tp - entry_mid) * 0.5
    else:
        return entry_mid - (entry_mid - tp) * 0.5


def _compute_pnl_R(entry_mid: float, exit_price: float, sl: float,
                   is_long: bool) -> float:
    """
    Compute P&L in R (risk units) from entry to exit, where 1R = entry-to-original-SL distance.
    """
    risk_distance = abs(entry_mid - sl)
    if risk_distance == 0:
        return 0.0
    raw_move = (exit_price - entry_mid) if is_long else (entry_mid - exit_price)
    return round(raw_move / risk_distance, 3)


def _check_time_out(row: dict, logged_at: datetime) -> bool:
    """Return True if trade has exceeded max_hold_hours."""
    max_hold = row.get("max_hold_hours") or DEFAULT_MAX_HOLD_HOURS
    age_hours = (datetime.now(timezone.utc) - logged_at).total_seconds() / 3600
    return age_hours >= max_hold


# ════════════════════════════════════════════════════════════
# CORE RESOLVER (v3)
# ════════════════════════════════════════════════════════════
def _hit_check(row: dict):
    """
    Return updated row if outcome resolved, else None.
    Resolution priority:
      0. Already resolved → skip
      1. Not a trade / missing fields → INVALID / NO_TRADE
      2. Stale signal → EXPIRED
      3. Entry never filled (75%+ aged) → NO_FILL
      4. Candle-by-candle scan post-fill:
         - Hit SL/TP (v2 same-candle logic) → SL / TP_HIT
         - Hit BE trigger → arm BE (set effective_sl = entry_mid)
         - Hit armed BE stop → BE_STOP
      5. Time-out check (every pass) → TIME_WIN / TIME_LOSS / TIME_FLAT
    """
    # ── Step 0: Already resolved
    if row.get("outcome") is not None:
        return None

    # ── Step 1a: Not a trade
    if row.get("position") not in ("LONG", "SHORT"):
        row["outcome"] = "NO_TRADE"
        row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
        row["win_loss_class"] = classify_outcome("NO_TRADE")
        return row

    # ── Step 1b: Missing required fields
    sl, tp = _get_effective_sl_tp(row)
    if not row.get("entry_zone") or sl is None or tp is None:
        row["outcome"] = "INVALID"
        row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
        row["win_loss_class"] = classify_outcome("INVALID")
        return row

    symbol = row.get("symbol")
    tf = _detect_timeframe(row)

    # Resolution config
    if "per_tf_details" in row or row.get("_format") == "multitf":
        resolution_tf = MULTITF_RESOLUTION
        max_age_days = MULTITF_MAX_AGE_DAYS
    else:
        resolution_tf = RESOLUTION_TF_MAP.get(tf, "15m")
        max_age_days = MAX_AGE_DAYS.get(tf, 5)

    # Parse logged_at
    logged_str = row.get("logged_at") or row.get("timestamp")
    if not logged_str:
        row["outcome"] = "INVALID"
        row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
        row["win_loss_class"] = classify_outcome("INVALID")
        return row
    try:
        logged = datetime.fromisoformat(logged_str.replace("Z", "+00:00"))
    except Exception:
        row["outcome"] = "INVALID"
        row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
        row["win_loss_class"] = classify_outcome("INVALID")
        return row

    # ── Step 2: Expiration check (v2)
    age = datetime.now(timezone.utc) - logged
    if age.days > max_age_days:
        row["outcome"] = "EXPIRED"
        row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
        row["expiration_age_days"] = age.days
        row["win_loss_class"] = classify_outcome("EXPIRED")
        return row

    # ── Step 3: Fetch klines
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

    # ── Step 4: Entry fill validation (v2)
    filled, fill_time = _entry_filled(row, df)
    if not filled:
        age_pct = age.total_seconds() / (max_age_days * 86400)
        if age_pct > 0.75:
            row["outcome"] = "NO_FILL"
            row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
            row["win_loss_class"] = classify_outcome("NO_FILL")
            return row

        # ── v3 NEW: Even if not filled, check time-out
        if _check_time_out(row, logged):
            row["outcome"] = "NO_FILL"
            row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
            row["outcome_note"] = "Time-out reached before entry filled"
            row["win_loss_class"] = classify_outcome("NO_FILL")
            return row
        return None

    row["entry_filled_at"] = (
        fill_time.isoformat() if hasattr(fill_time, "isoformat") else str(fill_time)
    )

    # ── Step 5: Scan candles post-fill for SL / TP / BE
    df_after_fill = df[df["timestamp"] >= pd.Timestamp(fill_time)].reset_index(drop=True)

    ez = row["entry_zone"]
    entry_mid = (float(ez["low"]) + float(ez["high"])) / 2
    is_long = row["position"] == "LONG"
    original_sl = sl  # for R calc

    # BE trigger price (50% of distance to TP)
    be_trigger = _compute_be_trigger(entry_mid, sl, tp, is_long, row)
    be_activated = row.get("be_activated", False)
    effective_sl = sl  # mutable — moves to entry_mid when BE arms

    for _, c in df_after_fill.iterrows():
        hi = float(c["high"])
        lo = float(c["low"])
        candle_ts = c["timestamp"]

        # Check BE arm (only if not yet armed)
        if not be_activated:
            be_hit_this_candle = (
                (is_long and hi >= be_trigger) or
                (not is_long and lo <= be_trigger)
            )
            if be_hit_this_candle:
                be_activated = True
                effective_sl = entry_mid
                row["be_activated"] = True
                row["be_activated_at"] = candle_ts.isoformat()
                row["stop_loss_effective"] = entry_mid
                # Continue to check TP / BE_STOP within same candle

        # Compute hits using current effective_sl
        if is_long:
            hit_sl = lo <= effective_sl
            hit_tp = hi >= tp
        else:
            hit_sl = hi >= effective_sl
            hit_tp = lo <= tp

        # Same-candle ambiguity → conservative (SL wins) — v2 behavior
        if hit_sl and hit_tp:
            outcome = "BE_STOP" if be_activated and effective_sl == entry_mid else "SL"
            exit_price = effective_sl
            row["outcome"] = outcome
            row["outcome_note"] = "SL + TP same candle — conservative resolution"
            row["pnl_pct"] = round(
                ((exit_price - entry_mid) / entry_mid * 100) if is_long
                else ((entry_mid - exit_price) / entry_mid * 100),
                2,
            )
            row["pnl_R"] = _compute_pnl_R(entry_mid, exit_price, original_sl, is_long)
            row["resolution_candle"] = candle_ts.isoformat()
            row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
            row["win_loss_class"] = classify_outcome(outcome)
            return row

        if hit_sl:
            outcome = "BE_STOP" if be_activated and effective_sl == entry_mid else "SL"
            exit_price = effective_sl
            row["outcome"] = outcome
            row["pnl_pct"] = round(
                ((exit_price - entry_mid) / entry_mid * 100) if is_long
                else ((entry_mid - exit_price) / entry_mid * 100),
                2,
            )
            row["pnl_R"] = _compute_pnl_R(entry_mid, exit_price, original_sl, is_long)
            row["resolution_candle"] = candle_ts.isoformat()
            row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
            row["win_loss_class"] = classify_outcome(outcome)
            return row

        if hit_tp:
            outcome = "TP_HIT"
            exit_price = tp
            row["outcome"] = outcome
            row["pnl_pct"] = round(
                ((exit_price - entry_mid) / entry_mid * 100) if is_long
                else ((entry_mid - exit_price) / entry_mid * 100),
                2,
            )
            row["pnl_R"] = _compute_pnl_R(entry_mid, exit_price, original_sl, is_long)
            row["resolution_candle"] = candle_ts.isoformat()
            row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
            row["win_loss_class"] = classify_outcome(outcome)
            return row

    # ── Step 6: Time-out check (v3 NEW)
    if _check_time_out(row, logged):
        # Force close at latest candle's close price
        last_close = float(df_after_fill.iloc[-1]["close"])
        pnl_R = _compute_pnl_R(entry_mid, last_close, original_sl, is_long)

        if pnl_R >= TIME_WIN_R_THRESHOLD:
            outcome = "TIME_WIN"
        elif pnl_R <= TIME_LOSS_R_THRESHOLD:
            outcome = "TIME_LOSS"
        else:
            outcome = "TIME_FLAT"

        row["outcome"] = outcome
        row["outcome_note"] = (
            f"Force-closed at time-out ({row.get('max_hold_hours', DEFAULT_MAX_HOLD_HOURS)}h) "
            f"@ {last_close:.4f}"
        )
        row["pnl_pct"] = round(
            ((last_close - entry_mid) / entry_mid * 100) if is_long
            else ((entry_mid - last_close) / entry_mid * 100),
            2,
        )
        row["pnl_R"] = pnl_R
        row["resolution_candle"] = df_after_fill.iloc[-1]["timestamp"].isoformat()
        row["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
        row["win_loss_class"] = classify_outcome(outcome)
        return row

    # Persist BE state even if not yet resolved (so it survives next pass)
    if be_activated:
        # Already saved earlier (be_activated, be_activated_at, stop_loss_effective)
        pass

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
    print(f"🔍 RESOLVER v3 — {len(pending)} pending of {len(rows)} total")
    print(f"{'='*60}\n")

    stats = {
        "TP_HIT": 0, "TP1": 0, "SL": 0, "BE_STOP": 0,
        "TIME_WIN": 0, "TIME_LOSS": 0, "TIME_FLAT": 0,
        "NO_FILL": 0, "EXPIRED": 0, "INVALID": 0, "NO_TRADE": 0,
        "skipped": 0,
    }
    be_armed_this_pass = 0
    updated_count = 0

    for r in rows:
        if r.get("outcome") is not None:
            continue

        was_be_activated = r.get("be_activated", False)
        result = _hit_check(r)

        if r.get("be_activated", False) and not was_be_activated:
            be_armed_this_pass += 1
            symbol = r.get("symbol", "?")
            print(f"  🟢 BE ARMED → {symbol}/{_detect_timeframe(r)}")

        if result is None:
            stats["skipped"] += 1
            continue

        outcome = result.get("outcome", "?")
        stats[outcome] = stats.get(outcome, 0) + 1
        updated_count += 1

        pnl = result.get("pnl_pct")
        pnl_R = result.get("pnl_R")
        pnl_str = ""
        if isinstance(pnl, (int, float)):
            pnl_str = f" ({pnl:+.2f}%"
            if isinstance(pnl_R, (int, float)):
                pnl_str += f", {pnl_R:+.2f}R"
            pnl_str += ")"
        symbol = result.get("symbol", "?")
        tf = _detect_timeframe(result)
        icon = _outcome_icon(outcome)
        print(f"  {icon} {symbol}/{tf}: {outcome}{pnl_str}")

    write_journal(rows)

    print(f"\n{'─'*60}")
    print(f"📊 RESOLUTION SUMMARY")
    print(f"{'─'*60}")
    print(f"  ✅ Resolved this pass:  {updated_count}")
    if be_armed_this_pass > 0:
        print(f"  🟢 BE armed this pass:  {be_armed_this_pass}")
    for k, v in stats.items():
        if v > 0 and k != "skipped":
            print(f"     {k:10s}: {v}")
    print(f"  ⏭️  Still open:          {stats['skipped']}")

    # Win rate (includes TIME_WIN as win, BE_STOP as flat)
    wins = stats["TP_HIT"] + stats["TP1"] + stats["TIME_WIN"]
    losses = stats["SL"] + stats["TIME_LOSS"]
    closed_total = wins + losses
    if closed_total > 0:
        wr = wins / closed_total * 100
        print(f"  🎯 Pass win rate:       {wr:.1f}% ({wins}W / {losses}L)")
    print(f"{'─'*60}\n")


def _outcome_icon(outcome: str) -> str:
    return {
        "TP_HIT": "✅", "TP1": "✅",
        "SL": "🛑", "BE_STOP": "🟦",
        "TIME_WIN": "⏰✅", "TIME_LOSS": "⏰🛑", "TIME_FLAT": "⏰⚪",
        "NO_FILL": "⊘", "EXPIRED": "⌛", "INVALID": "⚠️", "NO_TRADE": "—",
    }.get(outcome, "?")


if __name__ == "__main__":
    resolve_all()