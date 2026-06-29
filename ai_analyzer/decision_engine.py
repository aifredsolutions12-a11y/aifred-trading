"""
Decision engine — applies gates to confluence + EV.
Outputs LONG / SHORT / WAIT / HOLD with confidence tier.
"""
from typing import Dict, Optional
from ai_analyzer.confluence_engine import load_config


def decide_position(
    final_confluence: float,
    ev_R: float,
    timeframe: str = "4h",
    ev_threshold_pct: Optional[float] = None,
) -> dict:
    """
    Returns the position decision based on confluence + EV gates.
    """
    cfg = load_config()
    default_gates = cfg["default_gates"]
    tf_overrides = cfg.get("timeframe_gate_overrides", {}).get(timeframe, {})

    high = tf_overrides.get("confluence_high", default_gates["confluence_high"])
    medium = tf_overrides.get("confluence_medium", default_gates["confluence_medium"])
    low = tf_overrides.get("confluence_low", default_gates["confluence_low"])
    wait_low = default_gates["wait_band_low"]
    wait_high = default_gates["wait_band_high"]

    if ev_threshold_pct is None:
        ev_threshold_pct = cfg["ev_defaults"]["threshold_pct"]

    # Mirror gates for SHORT side
    short_high = 100 - high
    short_medium = 100 - medium
    short_low = 100 - low

    # Determine position
    if wait_low <= final_confluence <= wait_high:
        position = "WAIT"
        confidence = "SKIP"
        reason = f"In WAIT band ({wait_low}-{wait_high})"
    elif final_confluence >= high:
        position = "LONG"
        confidence = "HIGH"
        reason = f"Confluence {final_confluence} >= HIGH gate {high}"
    elif final_confluence >= medium:
        position = "LONG"
        confidence = "MEDIUM"
        reason = f"Confluence {final_confluence} >= MEDIUM gate {medium}"
    elif final_confluence >= low:
        position = "LONG"
        confidence = "LOW"
        reason = f"Confluence {final_confluence} >= LOW gate {low}"
    elif final_confluence <= short_high:
        position = "SHORT"
        confidence = "HIGH"
        reason = f"Confluence {final_confluence} <= SHORT-HIGH gate {short_high}"
    elif final_confluence <= short_medium:
        position = "SHORT"
        confidence = "MEDIUM"
        reason = f"Confluence {final_confluence} <= SHORT-MEDIUM gate {short_medium}"
    elif final_confluence <= short_low:
        position = "SHORT"
        confidence = "LOW"
        reason = f"Confluence {final_confluence} <= SHORT-LOW gate {short_low}"
    else:
        # Falls between LOW gates and WAIT band — bias to slightly favored side
        if final_confluence > 50:
            position = "LONG"
            confidence = "LOW"
            reason = f"Below LOW gate but >50, marginal LONG"
        else:
            position = "SHORT"
            confidence = "LOW"
            reason = f"Below LOW gate but <50, marginal SHORT"

    # EV gate (overrides confidence if EV is too weak)
    ev_pct = ev_R * 1.0  # in R-units, treat as percent for threshold check
    ev_passes = ev_pct >= (ev_threshold_pct / 100)  # convert pct threshold

    if position in ("LONG", "SHORT") and not ev_passes:
        if confidence in ("HIGH", "MEDIUM"):
            confidence = "LOW"
            reason += f" | EV {ev_R:+.3f}R below threshold → downgraded"

    return {
        "position":         position,
        "confidence":       confidence,
        "final_confluence": final_confluence,
        "ev_R":             ev_R,
        "ev_passes_gate":   ev_passes,
        "reason":           reason,
        "gates_used": {
            "long_high":     high,
            "long_medium":   medium,
            "long_low":      low,
            "short_high":    short_high,
            "short_medium":  short_medium,
            "short_low":     short_low,
            "wait_band":     [wait_low, wait_high],
            "ev_threshold":  ev_threshold_pct,
        },
    }