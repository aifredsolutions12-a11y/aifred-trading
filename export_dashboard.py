"""Export latest signals + postmortems + weights to docs/data/ for GitHub Pages."""
import json
from pathlib import Path
from collections import defaultdict

DOCS_DATA = Path("docs/data")
DOCS_DATA.mkdir(parents=True, exist_ok=True)


def export_signals():
    """Latest signal per coin → flat list."""
    signals_dir = Path("data/signals")
    if not signals_dir.exists():
        return

    latest_per_coin = {}
    for f in sorted(signals_dir.glob("*_multitf_*.json"), reverse=True):
        try:
            sig = json.loads(f.read_text(encoding="utf-8"))
            sym = sig.get("symbol")
            if sym and sym not in latest_per_coin:
                latest_per_coin[sym] = sig
        except Exception:
            continue

    out = sorted(latest_per_coin.values(), key=lambda s: s.get("symbol", ""))
    (DOCS_DATA / "signals_index.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"✅ Exported {len(out)} signals")


def export_postmortems():
    pm_dir = Path("data/postmortems")
    if not pm_dir.exists():
        return

    pms = []
    for f in sorted(pm_dir.glob("*.json"), reverse=True):
        try:
            pms.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue

    # Latest per coin
    by_coin = {}
    for pm in pms:
        coin = pm.get("coin")
        if coin and coin not in by_coin:
            by_coin[coin] = pm

    out = sorted(by_coin.values(), key=lambda p: p.get("coin", ""))
    (DOCS_DATA / "postmortems_index.json").write_text(json.dumps(out, indent=2))
    print(f"✅ Exported {len(out)} post-mortems")


def export_weights():
    w_dir = Path("data/adaptive_weights")
    if not w_dir.exists():
        return

    out = []
    for f in sorted(w_dir.glob("*_weights.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue

    (DOCS_DATA / "weights_index.json").write_text(json.dumps(out, indent=2))
    print(f"✅ Exported {len(out)} weight files")


if __name__ == "__main__":
    export_signals()
    export_postmortems()
    export_weights()