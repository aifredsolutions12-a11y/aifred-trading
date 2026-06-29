"""
Pure-Python confluence scoring engine.
No AI calls. 100% deterministic. Single source of math truth.
"""
from pathlib import Path
from typing import Dict, List
import yaml

CONFIG_PATH = Path("config/scoring_config.yaml")


# ════════════════════════════════════════════════════════════════
# CONFIG LOADER
# ════════════════════════════════════════════════════════════════
def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ════════════════════════════════════════════════════════════════
# CLASSICAL TA SCORE (no AI — fully deterministic)
# ════════════════════════════════════════════════════════════════
def compute_classical_ta_score(ta_snapshot: dict) -> dict:
    """
    Returns a 0-100 score from 8 classical TA signals.
    100 = strong long, 50 = neutral, 0 = strong short.
    """
    bullish = 0
    bearish = 0
    neutral = 0

    # 1. Trend (EMA50 vs EMA200)
    trend = str(ta_snapshot.get("trend", ""))
    if "BULLISH" in trend:
        bullish += 1
    elif "BEARISH" in trend:
        bearish += 1
    else:
        neutral += 1

    # 2-4. Price vs EMAs
    for ema_field in ["above_ema21", "above_ema50", "above_ema200"]:
        if ta_snapshot.get(ema_field):
            bullish += 1
        else:
            bearish += 1

    # 5. RSI (with explicit neutral band)
    rsi = ta_snapshot.get("rsi_14", 50)
    rsi_state = ta_snapshot.get("rsi_state", "Neutral")
    if rsi_state == "Oversold":
        bullish += 1
    elif rsi_state == "Overbought":
        bearish += 1
    elif rsi > 55:
        bullish += 1
    elif rsi < 45:
        bearish += 1
    else:
        neutral += 1

    # 6. MACD bias
    macd_bias = ta_snapshot.get("macd_bias", "Neutral")
    if macd_bias == "Bullish":
        bullish += 1
    elif macd_bias == "Bearish":
        bearish += 1
    else:
        neutral += 1

    # 7. MACD histogram
    hist = ta_snapshot.get("macd_histogram", 0)
    if hist > 0:
        bullish += 1
    elif hist < 0:
        bearish += 1
    else:
        neutral += 1

    # 8. Bollinger Band position (independent of MACD)
    bb_pos = ta_snapshot.get("bb_position_pct", 50)
    if bb_pos < 25:
        bullish += 1
    elif bb_pos > 75:
        bearish += 1
    else:
        neutral += 1

    total_directional = bullish + bearish
    score = (bullish / total_directional * 100) if total_directional > 0 else 50.0

    return {
        "score":            round(score, 1),
        "bullish_count":    bullish,
        "bearish_count":    bearish,
        "neutral_count":    neutral,
        "conviction_pct":   round(total_directional / 8 * 100, 1),
    }


# ════════════════════════════════════════════════════════════════
# SENTIMENT SCORE (contrarian)
# ════════════════════════════════════════════════════════════════
def compute_sentiment_score(blended_sentiment: float, funding_rate: float = None) -> float:
    """
    Contrarian sentiment scoring.
    Extreme fear/greed = strong contrarian signal.
    Funding rate amplifies at extremes.
    """
    if blended_sentiment is None:
        blended_sentiment = 50

    # Base contrarian mapping
    if blended_sentiment <= 20:
        score = 75   # extreme fear → contrarian long
    elif blended_sentiment <= 40:
        score = 60
    elif blended_sentiment >= 80:
        score = 25   # extreme greed → contrarian short
    elif blended_sentiment >= 60:
        score = 40
    else:
        score = 50

    # Funding amplifier
    if funding_rate is not None:
        if blended_sentiment >= 80 and funding_rate > 0.05:
            score = max(15, score - 10)
        elif blended_sentiment <= 20 and funding_rate < -0.02:
            score = min(85, score + 10)

    return round(score, 1)


# ════════════════════════════════════════════════════════════════
# EV EDGE SCORE
# ════════════════════════════════════════════════════════════════
def compute_ev_edge_score(win_prob_pct: float, rr_win: float = 2.0, rr_loss: float = 1.0) -> dict:
    """
    Computes EV in R-units and converts to 0-100 score.
    win_prob_pct: AI's estimated win probability (0-100)
    """
    wp = max(0, min(100, win_prob_pct)) / 100
    ev_R = (wp * rr_win) - ((1 - wp) * rr_loss)

    # Map EV_R to 0-100 score (centered at neutral)
    # EV_R = -1 → 0,  EV_R = 0 → 50,  EV_R = +1 → 100
    score = max(0, min(100, 50 + (ev_R * 50)))

    return {
        "ev_R":         round(ev_R, 4),
        "score":        round(score, 1),
        "win_prob":     round(win_prob_pct, 1),
    }


# ════════════════════════════════════════════════════════════════
# SINGLE-TIMEFRAME CONFLUENCE
# ════════════════════════════════════════════════════════════════
def compute_tf_confluence(method_scores: Dict[str, float], methodology_weights: Dict[str, float]) -> float:
    """
    Weighted blend of methodology scores for ONE timeframe.
    method_scores: {wyckoff, smc, elliott, classical_ta, sentiment, ev_edge} → 0-100 each
    methodology_weights: same keys → must sum to 1.0
    """
    total = 0.0
    for method, score in method_scores.items():
        weight = methodology_weights.get(method, 0)
        total += score * weight
    return round(total, 2)


# ════════════════════════════════════════════════════════════════
# MULTI-TIMEFRAME AGGREGATION
# ════════════════════════════════════════════════════════════════
def aggregate_multi_tf_confluence(
    tf_confluences: Dict[str, float],
    tf_weights: Dict[str, float] = None,
) -> dict:
    """
    Combines per-TF confluence scores into one verdict score.
    tf_confluences: {"15m": 62, "4h": 71, "1d": 75, ...}
    tf_weights: loaded from scoring_config.yaml if not provided
    """
    if tf_weights is None:
        tf_weights = load_config()["timeframe_weights"]

    weighted_sum = 0.0
    total_weight = 0.0
    trail = []

    for tf, score in tf_confluences.items():
        w = tf_weights.get(tf, 0)
        contribution = score * w
        weighted_sum += contribution
        total_weight += w
        trail.append({
            "tf":           tf,
            "score":        round(score, 1),
            "weight":       w,
            "contribution": round(contribution, 2),
        })

    if total_weight == 0:
        final = 50.0
    else:
        final = weighted_sum / total_weight

    return {
        "final_confluence": round(final, 2),
        "tf_trail":         trail,
        "total_weight":     round(total_weight, 4),
    }


# ════════════════════════════════════════════════════════════════
# WEIGHT NORMALIZER (utility)
# ════════════════════════════════════════════════════════════════
def normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """Ensures weights sum to 1.0 by proportional scaling."""
    total = sum(weights.values())
    if total == 0:
        return {k: 0 for k in weights}
    return {k: round(v / total, 4) for k, v in weights.items()}