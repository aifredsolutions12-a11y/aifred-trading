"""
Classical TA confluence counter + preliminary score blender.
"""

def count_bullish_bearish(ta: dict) -> dict:
    """Count bullish vs bearish signals from indicator snapshot."""
    bull = 0
    bear = 0

    # Trend
    if "BULLISH" in (ta.get("trend") or ""):
        bull += 1
    else:
        bear += 1

    # EMA positioning
    if ta.get("above_ema21"):  bull += 1
    else:                       bear += 1
    if ta.get("above_ema50"):  bull += 1
    else:                       bear += 1
    if ta.get("above_ema200"): bull += 1
    else:                       bear += 1

    # RSI
    rsi = ta.get("rsi_14", 50)
    state = ta.get("rsi_state", "Neutral")
    if state == "Oversold":     bull += 1   # mean-reversion bias
    elif state == "Overbought": bear += 1
    elif rsi > 55:              bull += 1
    elif rsi < 45:              bear += 1

    # MACD
    if ta.get("macd_bias") == "Bullish": bull += 1
    else:                                 bear += 1
    if (ta.get("macd_histogram") or 0) > 0: bull += 1
    else:                                    bear += 1

    # Bollinger Band position
    bb_pos = ta.get("bb_position_pct", 50)
    if bb_pos < 20:   bull += 1   # near lower band
    elif bb_pos > 80: bear += 1   # near upper band

    total = bull + bear
    classical_pct = round((bull / total) * 100, 1) if total else 50.0

    return {
        "bullish_count": bull,
        "bearish_count": bear,
        "total_signals": total,
        "classical_ta_pct": classical_pct,
    }


def preliminary_confluence(ta_counts: dict, blended_sentiment: float) -> dict:
    """Blend classical TA bull% (60%) with sentiment score (40%)."""
    ta_pct = ta_counts.get("classical_ta_pct", 50.0)
    # blended_sentiment is -1..+1 -> map to 0..100
    sent_bull_pct = (blended_sentiment + 1) / 2 * 100
    score = round(ta_pct * 0.60 + sent_bull_pct * 0.40, 1)

    if score >= 65:   bias = "Bullish"
    elif score >= 55: bias = "Mildly Bullish"
    elif score <= 35: bias = "Bearish"
    elif score <= 45: bias = "Mildly Bearish"
    else:             bias = "Neutral"

    return {
        "preliminary_score": score,
        "preliminary_bias": bias,
        "ta_component": ta_pct,
        "sentiment_component": round(sent_bull_pct, 1),
    }
