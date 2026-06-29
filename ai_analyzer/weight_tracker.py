"""
Adaptive methodology weight tracker.
Reads closed trade outcomes from memory journal and adjusts weights per coin.
"""
import json
from pathlib import Path
from typing import Dict, List
from collections import defaultdict

from ai_analyzer.confluence_engine import load_config, normalize_weights

WEIGHTS_DIR = Path("data/adaptive_weights")
WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)


def get_weights_path(coin: str) -> Path:
    return WEIGHTS_DIR / f"{coin}_weights.json"


def load_adaptive_weights(coin: str) -> Dict[str, float]:
    """Load coin-specific adjusted weights, or fall back to base."""
    path = get_weights_path(coin)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("weights", load_config()["methodology_weights_base"])
        except Exception:
            pass
    return load_config()["methodology_weights_base"].copy()


def save_adaptive_weights(coin: str, weights: Dict[str, float], metadata: dict = None):
    """Persist adjusted weights for a coin."""
    path = get_weights_path(coin)
    payload = {
        "coin":     coin,
        "weights":  weights,
        "metadata": metadata or {},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def compute_method_winrate(
    closed_trades: List[dict],
    method_score_field: str = "method_scores",
    high_threshold: int = 70,
    low_threshold: int = 30,
) -> Dict[str, float]:
    """
    For each methodology, computes win rate when it was CONFIDENT.
    A method is 'confident' when its score >= high_threshold (bullish call)
    or <= low_threshold (bearish call).
    """
    method_stats = defaultdict(lambda: {"wins": 0, "losses": 0})

    for trade in closed_trades:
        scores = trade.get(method_score_field, {})
        outcome = trade.get("outcome")
        position = trade.get("position")

        if outcome not in ("TP1", "SL") or position not in ("LONG", "SHORT"):
            continue

        is_win = outcome == "TP1"

        for method, score in scores.items():
            if not isinstance(score, (int, float)):
                continue

            # Was this method confidently bullish or bearish?
            if position == "LONG" and score >= high_threshold:
                method_stats[method]["wins" if is_win else "losses"] += 1
            elif position == "SHORT" and score <= low_threshold:
                method_stats[method]["wins" if is_win else "losses"] += 1

    win_rates = {}
    for method, stats in method_stats.items():
        total = stats["wins"] + stats["losses"]
        if total > 0:
            win_rates[method] = {
                "win_rate": stats["wins"] / total,
                "samples":  total,
                "wins":     stats["wins"],
                "losses":   stats["losses"],
            }

    return win_rates


def adjust_weights_for_coin(coin: str, closed_trades: List[dict]) -> dict:
    """
    Main entry — recalculates and saves adaptive weights for one coin.
    """
    cfg = load_config()
    base = cfg["methodology_weights_base"].copy()
    settings = cfg["adaptive_weights"]

    if not settings.get("enabled", True):
        return {"weights": base, "adjusted": False, "reason": "disabled"}

    min_samples = settings.get("min_samples_per_coin", 20)
    max_drift = settings.get("max_drift_pct", 0.10)
    boost_threshold = settings.get("win_rate_boost_threshold", 0.55)
    cut_threshold = settings.get("win_rate_cut_threshold", 0.45)

    win_rates = compute_method_winrate(closed_trades)

    adjusted = base.copy()
    notes = []

    for method, base_weight in base.items():
        if method not in win_rates:
            continue
        stats = win_rates[method]
        if stats["samples"] < min_samples:
            notes.append(f"{method}: only {stats['samples']} samples, no adjust")
            continue

        wr = stats["win_rate"]
        if wr >= boost_threshold:
            # Boost up to max_drift
            boost = min(max_drift, (wr - 0.5) * 0.4)
            adjusted[method] = base_weight * (1 + boost)
            notes.append(f"{method}: WR {wr:.0%} → +{boost*100:.1f}%")
        elif wr <= cut_threshold:
            # Cut down to max_drift
            cut = min(max_drift, (0.5 - wr) * 0.4)
            adjusted[method] = base_weight * (1 - cut)
            notes.append(f"{method}: WR {wr:.0%} → -{cut*100:.1f}%")

    # Normalize so weights sum to 1.0
    final = normalize_weights(adjusted)

    save_adaptive_weights(coin, final, metadata={
        "win_rates": win_rates,
        "notes":     notes,
        "base":      base,
    })

    return {
        "weights":   final,
        "adjusted":  True,
        "win_rates": win_rates,
        "notes":     notes,
    }