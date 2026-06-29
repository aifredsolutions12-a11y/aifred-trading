"""
Loads coins.yaml with global timeframe defaults + per-coin overrides.
"""
import yaml
from pathlib import Path


CONFIG_PATH = Path("config/coins.yaml")

VALID_TIMEFRAMES = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h",
                    "6h", "8h", "12h", "1d", "3d", "1w"}


class ConfigError(Exception):
    pass


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise ConfigError(f"Config file not found: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_active_coins() -> list:
    """All active coin entries from watchlist."""
    cfg = load_config()
    return [c for c in cfg["watchlist"] if c.get("active", False)]


def list_active_symbols() -> list:
    return [c["symbol"] for c in list_active_coins()]


def get_timeframe_config(symbol: str, timeframe: str) -> dict:
    """Merged config: global timeframe defaults + per-coin override."""
    cfg = load_config()

    if timeframe not in VALID_TIMEFRAMES:
        raise ConfigError(
            f"Invalid timeframe '{timeframe}'. Valid: {sorted(VALID_TIMEFRAMES)}"
        )

    coin = next(
        (c for c in cfg["watchlist"] if c["symbol"].upper() == symbol.upper()),
        None
    )
    if coin is None:
        raise ConfigError(f"Symbol {symbol} not in watchlist")

    tf_defaults = cfg.get("timeframe_defaults", {})
    if timeframe not in tf_defaults:
        raise ConfigError(f"Timeframe '{timeframe}' has no default profile")

    base = dict(tf_defaults[timeframe])

    # Apply per-coin override if present
    coin_overrides = coin.get("timeframe_overrides", {}).get(timeframe, {})
    base.update(coin_overrides)

    base["symbol"] = symbol
    base["name"] = coin.get("name", symbol)
    base["timeframe"] = timeframe
    base["category"] = coin.get("category", "unknown")
    base["rank"] = coin.get("rank", 999)

    return base


def get_bankroll() -> dict:
    return load_config().get("bankroll", {})


def get_top_tier() -> list:
    return load_config().get("top_tier_symbols", [])


def list_scheduler_targets() -> list:
    """All (symbol, timeframe) combos where scheduler_active=true."""
    cfg = load_config()
    tf_defaults = cfg.get("timeframe_defaults", {})
    targets = []
    for coin in cfg["watchlist"]:
        if not coin.get("active", False):
            continue
        for tf, tf_cfg in tf_defaults.items():
            overrides = coin.get("timeframe_overrides", {}).get(tf, {})
            merged = {**tf_cfg, **overrides}
            if merged.get("scheduler_active", False):
                targets.append((coin["symbol"], tf))
    return targets


def get_default_symbol() -> str:
    return load_config().get("default_symbol", "BTCUSDT")


def get_default_timeframe() -> str:
    return load_config().get("default_timeframe", "4h")


if __name__ == "__main__":
    print(f"✅ Active coins: {len(list_active_coins())}")
    for c in list_active_coins():
        print(f"   #{c['rank']:2d}  {c['symbol']:10s} {c['name']} ({c['category']})")
    print(f"\n✅ Top tier: {get_top_tier()}")
    targets = list_scheduler_targets()
    print(f"\n✅ Scheduler-active targets: {len(targets)}")
