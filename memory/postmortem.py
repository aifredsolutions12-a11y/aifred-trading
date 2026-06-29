"""
Post-mortem engine — runs ONCE daily.
Generates AI lessons for newly closed trades (TP1 or SL).
Saves lessons per coin for memory injection in next analysis.
"""
import os
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

from dotenv import load_dotenv
import google.generativeai as genai

from memory.journal import read_journal, write_journal

load_dotenv("config/.env")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

MODEL_NAME = "gemini-2.0-flash-lite"
POSTMORTEM_DIR = Path("data/postmortems")
POSTMORTEM_DIR.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════
def _clean_json(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _summarize_trade(t: dict) -> str:
    """Compact one-trade summary for the AI prompt."""
    return (
        f"  - {t.get('symbol')} {t.get('position')} "
        f"({t.get('confidence', '?')}) "
        f"conf={t.get('final_confluence') or t.get('confluence_score', '?')} "
        f"win_prob={t.get('estimated_win_prob_pct', '?')}% "
        f"→ {t.get('outcome')} ({t.get('pnl_pct', 0):+.2f}%) "
        f"narrative: {(t.get('final_narrative') or t.get('final_verdict') or '')[:200]}"
    )


def _build_postmortem_prompt(coin: str, recent_closed: list) -> str:
    """Build a single prompt for all recently closed trades of one coin."""
    trade_block = "\n".join(_summarize_trade(t) for t in recent_closed)
    wins = sum(1 for t in recent_closed if t.get("outcome") == "TP1")
    losses = sum(1 for t in recent_closed if t.get("outcome") == "SL")

    return f"""You are a trading coach reviewing the last {len(recent_closed)} closed trades for {coin}.

Recent trades:
{trade_block}

Recent record: {wins}W / {losses}L

Your task — write a SHORT, ACTIONABLE post-mortem (2-3 sentences) covering:
1. What pattern emerged in the wins or losses?
2. What was the system getting wrong (or right)?
3. ONE concrete adjustment for next analysis on {coin}.

Be specific. Use the trade data. Reference methodologies (Wyckoff, SMC, Elliott).
Do NOT generalize ("trade better"). Do NOT moralize.

Return ONLY valid JSON:
{{
  "coin": "{coin}",
  "date": "{datetime.now(timezone.utc).date().isoformat()}",
  "trades_reviewed": {len(recent_closed)},
  "wins": {wins},
  "losses": {losses},
  "lesson": "<your 2-3 sentence post-mortem>",
  "adjustment": "<one concrete behavioral change for next analysis>",
  "methodology_flag": "<which methodology should be trusted MORE or LESS, e.g. 'Trust SMC less on alts'>"
}}
"""


def _call_gemini(prompt: str) -> dict:
    try:
        model = genai.GenerativeModel(
            MODEL_NAME,
            generation_config={
                "temperature": 0.3,
                "response_mime_type": "application/json",
            },
        )
        response = model.generate_content(prompt)
        raw = response.text or ""
        return json.loads(_clean_json(raw))
    except Exception as e:
        return {"error": f"Postmortem failed: {e}"}


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════
def run_daily_postmortem(lookback_hours: int = 24):
    """
    Find all trades closed in the last `lookback_hours` and generate
    one post-mortem per coin (batched).
    """
    print(f"\n{'='*60}")
    print(f"📝 DAILY POST-MORTEM ENGINE")
    print(f"{'='*60}\n")

    rows = read_journal()
    cutoff = datetime.now(timezone.utc).timestamp() - (lookback_hours * 3600)

    # Find recently resolved
    newly_closed = []
    for r in rows:
        if r.get("outcome") not in ("TP1", "SL"):
            continue
        resolved_at = r.get("outcome_resolved_at")
        if not resolved_at:
            continue
        try:
            ts = datetime.fromisoformat(resolved_at.replace("Z", "+00:00")).timestamp()
            if ts >= cutoff:
                # Only run once per trade
                if not r.get("postmortem_generated"):
                    newly_closed.append(r)
        except Exception:
            continue

    if not newly_closed:
        print("✅ No new closed trades to review.")
        return

    print(f"🔍 Found {len(newly_closed)} newly closed trades")

    # Group by coin
    by_coin = defaultdict(list)
    for t in newly_closed:
        by_coin[t.get("symbol", "?")].append(t)

    print(f"📊 Grouped into {len(by_coin)} coins\n")

    # One AI call per coin
    for coin, trades in by_coin.items():
        print(f"  🧠 {coin}: reviewing {len(trades)} trade(s)...")

        # Pull last 10 closed for that coin (gives AI context)
        all_closed_for_coin = [
            r for r in rows
            if r.get("symbol") == coin and r.get("outcome") in ("TP1", "SL")
        ]
        recent_for_review = all_closed_for_coin[-10:]

        prompt = _build_postmortem_prompt(coin, recent_for_review)
        result = _call_gemini(prompt)

        if "error" in result:
            print(f"     ❌ {result['error']}")
            continue

        # Save post-mortem file
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        out_path = POSTMORTEM_DIR / f"{coin}_{ts_str}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        print(f"     ✅ Saved: {out_path.name}")
        print(f"     💡 {result.get('lesson', '')[:150]}")

        # Mark trades as reviewed
        for t in trades:
            t["postmortem_generated"] = True
            t["postmortem_file"] = str(out_path.name)

    # Persist journal updates
    write_journal(rows)
    print(f"\n{'─'*60}")
    print(f"✅ Daily post-mortem complete")
    print(f"{'─'*60}\n")


if __name__ == "__main__":
    run_daily_postmortem()