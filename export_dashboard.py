"""Export latest signals + postmortems + weights to docs/data/ for GitHub Pages."""
import json
from pathlib import Path

DOCS_DATA = Path("docs/data")
DOCS_DATA.mkdir(parents=True, exist_ok=True)


def export_signals():
    """Read all *_latest.json files → flat list."""
    signals_dir = Path("data/signals")
    if not signals_dir.exists():
        return

    out = []
    for f in sorted(signals_dir.glob("*_latest.json")):
        try:
            sig = json.loads(f.read_text(encoding="utf-8"))
            out.append(sig)
        except Exception as e:
            print(f"⚠️ Could not read {f.name}: {e}")
            continue

    # Sort by symbol
    out.sort(key=lambda s: s.get("symbol", ""))
    (DOCS_DATA / "signals_index.json").write_text(
        json.dumps(out, indent=2, default=str)
    )
    print(f"✅ Exported {len(out)} latest signals")


def export_position_status():
    """
    Read journal + extract currently open positions with refresh metadata.
    Powers the new 'Position Status' section in the dashboard.
    """
    journal_path = Path("data/journal.jsonl")
    if not journal_path.exists():
        return

    try:
        with open(journal_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Handle both JSON array and JSONL formats
        if content.strip().startswith("["):
            journal = json.loads(content)
        else:
            journal = [json.loads(line) for line in content.splitlines() if line.strip()]
    except Exception as e:
        print(f"⚠️ Could not read journal: {e}")
        return

    open_positions = [
        t for t in journal
        if t.get("outcome") is None
        and t.get("position") in ("LONG", "SHORT")
    ]

    status_list = []
    for p in open_positions:
        status_list.append({
            "symbol": p.get("symbol"),
            "position": p.get("position"),
            "confidence": p.get("confidence"),
            "entry_zone": p.get("entry_zone"),
            "stop_loss": p.get("stop_loss"),
            "take_profit_1": p.get("take_profit_1"),
            "logged_at": p.get("logged_at"),
            "refresh_count": p.get("_refresh_count", 0),
            "last_refresh_at": p.get("_last_refresh_at"),
            "latest_confluence": p.get("_latest_confluence"),
            "latest_confidence": p.get("_latest_confidence"),
            "latest_ev_R": p.get("_latest_ev_R"),
            "original_confluence": p.get("final_confluence"),
        })

    (DOCS_DATA / "position_status.json").write_text(
        json.dumps(status_list, indent=2, default=str)
    )
    print(f"✅ Exported {len(status_list)} open positions")


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
    (DOCS_DATA / "postmortems_index.json").write_text(
        json.dumps(out, indent=2)
    )
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
    export_position_status()
    export_postmortems()
    export_weights()