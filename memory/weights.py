"""
Auto-tune confluence method weights based on rolling performance.

Rule: methods with above-average win rate get a tiny boost, below-average get a tiny cut.
Adjustments are capped at ±0.05 per cycle and re-normalized to sum=1.0.
"""
import json
from pathlib import Path
from memory.stats import compute_stats

WEIGHTS_PATH = Path("config/weights.json")
DEFAULT = {
    "wyckoff": 0.20,
    "smc": 0.20,
    "elliott": 0.15,
    "classical_ta": 0.20,
    "sentiment": 0.15,
    "ev_edge": 0.10,
}
MIN_TRADES_TO_TUNE = 20
MAX_ADJUSTMENT = 0.05


def load_weights() -> dict:
    if WEIGHTS_PATH.exists():
        try:
            return json.loads(WEIGHTS_PATH.read_text())
        except json.JSONDecodeError:
            pass
    save_weights(DEFAULT)
    return dict(DEFAULT)


def save_weights(w: dict):
    WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEIGHTS_PATH.write_text(json.dumps(w, indent=2))


def auto_tune() -> dict:
    """Adjust weights toward better-performing methods."""
    stats = compute_stats()
    if stats["trades"] < MIN_TRADES_TO_TUNE:
        print(f"⏭️  Need {MIN_TRADES_TO_TUNE} trades to tune, have {stats['trades']}")
        return load_weights()

    w = load_weights()
    perf = stats["by_method"]
    if not perf:
        return w

    avg_wr = sum(p["win_rate"] for p in perf.values()) / len(perf)
    for method, p in perf.items():
        if method not in w:
            continue
        delta = (p["win_rate"] - avg_wr) / 100 * MAX_ADJUSTMENT
        w[method] = max(0.05, min(0.40, w[method] + delta))

    total = sum(w.values()) or 1.0
    w = {k: round(v / total, 4) for k, v in w.items()}
    save_weights(w)
    print(f"✅ Weights auto-tuned: {w}")
    return w


if __name__ == "__main__":
    auto_tune()
