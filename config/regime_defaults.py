"""
Timeframe-specific defaults — loaded from scoring_config.yaml.
This file exists for backwards compatibility with config_loader.
"""
from pathlib import Path
import yaml

SCORING_CONFIG_PATH = Path("config/scoring_config.yaml")


def load_scoring_config() -> dict:
    """Single source of truth for all weights and gates."""
    with open(SCORING_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_timeframe_defaults() -> dict:
    """Returns per-timeframe config compatible with old analyzer.py."""
    cfg = load_scoring_config()
    tf_overrides = cfg.get("timeframe_gate_overrides", {})
    default_gates = cfg.get("default_gates", {})
    ev_def = cfg.get("ev_defaults", {})

    defaults = {}
    for tf, weight in cfg["timeframe_weights"].items():
        gates = {**default_gates, **tf_overrides.get(tf, {})}
        defaults[tf] = {
            "weight":            weight,
            "ev_threshold":      ev_def.get("threshold_pct", 3.0),
            "confluence_high":   gates["confluence_high"],
            "confluence_medium": gates["confluence_medium"],
            "confluence_low":    gates["confluence_low"],
            "wait_band_low":     default_gates["wait_band_low"],
            "wait_band_high":    default_gates["wait_band_high"],
            "use_news":          tf in ("4h", "1d", "1w"),
            "use_fng":           tf in ("4h", "1d", "1w"),
            "candles":           500 if tf in ("1d", "1w") else 300,
        }
    return defaults


TIMEFRAME_DEFAULTS = get_timeframe_defaults()