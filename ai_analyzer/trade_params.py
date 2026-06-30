"""
Trade parameter computer — v3.
Takes the AI's verdict + indicator snapshot and enriches with:
- ATR-based SL/TP
- Blended effective SL/TP (midpoint of AI + ATR, clipped to ±50% guardrail)
- Break-even trigger price
- Max-hold hours (based on TF + confidence)

ZERO AI calls. Pure code. Imports nothing from analyzer.py to avoid circular deps.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import yaml

CONFIG_PATH = Path("config/coins.yaml")


# ════════════════════════════════════════════════════════════
# CONFIG LOADER
# ════════════════════════════════════════════════════════════
_CACHED_CFG: Optional[dict] = None

def _load_cfg() -> dict:
    global _CACHED_CFG
    if _CACHED_CFG is None:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _CACHED_CFG = yaml.safe_load(f)
    return _CACHED_CFG


def _get_coin_tier(symbol: str) -> int:
    """Look up coin tier from watchlist. Default to 2 (standard alt) if missing."""
    cfg = _load_cfg()
    watchlist = cfg.get("watchlist", {})
    for _name, entry in watchlist.items():
        if entry.get("symbol", "").upper() == symbol.upper():
            return int(entry.get("tier", 2))
    return 2  # default to tier 2 for any coin not explicitly listed


def _get_multipliers(symbol: str) -> dict:
    """Return {'sl_mult': X, 'tp_mult': Y} for the coin's tier."""
    tier = _get_coin_tier(symbol)
    cfg = _load_cfg()
    atr_cfg = cfg.get("atr_multipliers", {})
    tier_key = f"tier_{tier}"
    return atr_cfg.get(tier_key, atr_cfg.get("tier_2", {"sl_mult": 1.5, "tp_mult": 2.5}))


def _get_guardrail_pct() -> float:
    cfg = _load_cfg()
    return float(cfg.get("atr_blend", {}).get("guardrail_pct", 0.50))


def _get_max_hold_hours(timeframe: str, confidence: int) -> float:
    """Look up base max-hold for TF + apply confidence boost."""
    cfg = _load_cfg()
    base_map = cfg.get("max_hold_defaults", {})
    base = float(base_map.get(timeframe, 24))  # safe default 24h

    boost_cfg = cfg.get("max_hold_confidence_boost", {})
    conf = int(confidence or 0)

    if conf >= boost_cfg.get("high_threshold", 50):
        return base * boost_cfg.get("high_boost", 1.50)
    if conf < boost_cfg.get("very_weak_below", 20):
        return base * boost_cfg.get("very_weak_boost", 0.50)
    if conf < boost_cfg.get("weak_low", 20) + (boost_cfg.get("medium_low", 35) - boost_cfg.get("weak_low", 20)):
        # 20-34 → weak
        if conf < boost_cfg.get("medium_low", 35):
            return base * boost_cfg.get("weak_boost", 0.75)
    return base  # 35-49 → base


# ════════════════════════════════════════════════════════════
# ATR-BASED SL/TP COMPUTATION
# ════════════════════════════════════════════════════════════
def _compute_atr_sl_tp(
    entry_mid: float,
    atr: float,
    is_long: bool,
    sl_mult: float,
    tp_mult: float,
) -> tuple[float, float]:
    """Return (atr_sl, atr_tp) using entry_mid ± multiplier × ATR."""
    if is_long:
        atr_sl = entry_mid - sl_mult * atr
        atr_tp = entry_mid + tp_mult * atr
    else:
        atr_sl = entry_mid + sl_mult * atr
        atr_tp = entry_mid - tp_mult * atr
    return atr_sl, atr_tp


def _clip_to_guardrail(
    ai_value: Optional[float],
    atr_value: float,
    guardrail_pct: float,
) -> float:
    """
    If AI's value is further than guardrail_pct from ATR-based, clip it.
    Returns the clipped (or untouched) value to use in midpoint calc.
    """
    if ai_value is None:
        return atr_value
    try:
        ai_value = float(ai_value)
    except (TypeError, ValueError):
        return atr_value

    max_deviation = abs(atr_value) * guardrail_pct
    upper = atr_value + max_deviation
    lower = atr_value - max_deviation
    return max(lower, min(upper, ai_value))


def _blend_midpoint(ai_clipped: float, atr_value: float) -> float:
    """Midpoint of AI-clipped value and ATR-based value."""
    return round((ai_clipped + atr_value) / 2, 8)


# ════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ════════════════════════════════════════════════════════════
def compute_trade_params(
    verdict: dict,
    symbol: str,
    timeframe: str,
    confidence_score: Optional[float] = None,
    ta_snapshot: Optional[dict] = None,
) -> dict:
    """
    Enrich a verdict dict with ATR-based SL/TP, BE trigger, max_hold_hours.

    Args:
        verdict: AI's verdict dict. Must have position, entry_zone, stop_loss, take_profit_1.
        symbol: e.g. "BTCUSDT"
        timeframe: trade's primary TF, e.g. "4h"
        confidence_score: numeric confidence (your typical range 0-50)
        ta_snapshot: output from summarize_indicators() — needs 'atr_14' key

    Returns:
        Same verdict dict mutated with new fields:
          stop_loss_ai, take_profit_ai          (mirror of AI's raw output)
          stop_loss_atr, take_profit_atr         (pure ATR-based)
          stop_loss_effective, take_profit_effective  (blended midpoint)
          atr_at_entry, atr_pct, atr_tf
          be_trigger_price
          max_hold_hours

    Behavior:
        - If position is WAIT/SKIP/HOLD or not LONG/SHORT → returns verdict unchanged
        - If ta_snapshot has no ATR → falls back to AI values (no ATR enrichment)
        - If AI has no SL/TP → uses pure ATR-based
        - AI's SL/TP clipped to ±guardrail_pct of ATR before midpoint blend
    """
    position = verdict.get("position", "").upper()

    # ── Skip non-actionable verdicts entirely (Q5 confirmed) ──
    if position not in ("LONG", "SHORT"):
        return verdict

    is_long = position == "LONG"

    # ── Validate entry zone ──
    ez = verdict.get("entry_zone") or {}
    try:
        ez_low = float(ez.get("low"))
        ez_high = float(ez.get("high"))
    except (TypeError, ValueError):
        # No entry zone → can't compute ATR levels; return as-is
        return verdict
    entry_mid = (ez_low + ez_high) / 2

    # ── Get ATR ──
    atr = None
    atr_pct = None
    if ta_snapshot:
        atr = ta_snapshot.get("atr_14")
        atr_pct = ta_snapshot.get("volatility_pct")
    try:
        atr = float(atr) if atr is not None else None
    except (TypeError, ValueError):
        atr = None

    # ── Mirror AI values ──
    ai_sl = verdict.get("stop_loss")
    ai_tp = verdict.get("take_profit_1")

    verdict["stop_loss_ai"] = ai_sl
    verdict["take_profit_ai"] = ai_tp

    # ── Compute max_hold_hours (works even without ATR) ──
    verdict["max_hold_hours"] = round(
        _get_max_hold_hours(timeframe, confidence_score or 0), 1
    )

    # ── If no ATR available, fall back to AI values for effective levels ──
    if atr is None or atr <= 0:
        verdict["stop_loss_atr"] = None
        verdict["take_profit_atr"] = None
        verdict["stop_loss_effective"] = ai_sl
        verdict["take_profit_effective"] = ai_tp
        verdict["atr_at_entry"] = None
        verdict["atr_pct"] = None
        verdict["atr_tf"] = timeframe
        verdict["be_trigger_price"] = _compute_be_trigger(
            entry_mid, ai_tp, is_long
        ) if ai_tp is not None else None
        return verdict

    # ── Get multipliers + guardrail ──
    mults = _get_multipliers(symbol)
    sl_mult = float(mults.get("sl_mult", 1.5))
    tp_mult = float(mults.get("tp_mult", 2.5))
    guardrail_pct = _get_guardrail_pct()

    # ── Compute ATR-based SL/TP ──
    atr_sl, atr_tp = _compute_atr_sl_tp(entry_mid, atr, is_long, sl_mult, tp_mult)

    # ── Clip AI values within guardrail of ATR, then midpoint blend ──
    ai_sl_clipped = _clip_to_guardrail(ai_sl, atr_sl, guardrail_pct)
    ai_tp_clipped = _clip_to_guardrail(ai_tp, atr_tp, guardrail_pct)

    effective_sl = _blend_midpoint(ai_sl_clipped, atr_sl)
    effective_tp = _blend_midpoint(ai_tp_clipped, atr_tp)

    # ── Compute BE trigger at 50% of effective TP distance ──
    be_trigger = _compute_be_trigger(entry_mid, effective_tp, is_long)

    # ── Inject all v3 fields ──
    verdict["stop_loss_atr"]  = round(atr_sl, 8)
    verdict["take_profit_atr"] = round(atr_tp, 8)
    verdict["stop_loss_effective"]  = effective_sl
    verdict["take_profit_effective"] = effective_tp
    verdict["atr_at_entry"] = round(atr, 8)
    verdict["atr_pct"] = round(atr_pct, 3) if atr_pct is not None else None
    verdict["atr_tf"] = timeframe
    verdict["be_trigger_price"] = round(be_trigger, 8)

    return verdict


def _compute_be_trigger(entry_mid: float, effective_tp: float, is_long: bool) -> float:
    """BE trigger = 50% of distance from entry to effective TP."""
    if is_long:
        return entry_mid + (effective_tp - entry_mid) * 0.5
    else:
        return entry_mid - (entry_mid - effective_tp) * 0.5