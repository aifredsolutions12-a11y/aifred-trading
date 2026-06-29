"""
Multi-TF AI Analyzer (v4)
- 1 Gemini call per coin (all 6 TFs analyzed together)
- Code-driven confluence (no AI math)
- Adaptive methodology weights per coin
- Memory injection (past verdicts + outcomes)
- Post-mortem awareness
"""
import os
import json
import re
import argparse
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv
import google.generativeai as genai

from data_collector.chart_data import (
    fetch_klines, fetch_current_price, fetch_funding_rate, validate_interval
)
from data_collector.indicators import compute_indicators, summarize_indicators
from data_collector.context_builder import build_context

from ai_analyzer.confluence_engine import (
    load_config,
    compute_classical_ta_score,
    compute_sentiment_score,
    compute_ev_edge_score,
    compute_tf_confluence,
    aggregate_multi_tf_confluence,
)
from ai_analyzer.decision_engine import decide_position
from ai_analyzer.weight_tracker import load_adaptive_weights
from ai_analyzer.memory import build_memory_block, load_closed_trades

load_dotenv("config/.env")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

MODEL_NAME = "gemini-3.1-flash-lite"
PROMPT_PATH = Path("ai_analyzer/prompt_template.txt")
SIGNALS_DIR = Path("data/signals")
SIGNALS_DIR.mkdir(parents=True, exist_ok=True)

TIMEFRAMES = ["15m", "30m", "1h", "4h", "1d", "1w"]


# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════
def _format_headlines(news, max_items=8):
    if not news or not news.get("headlines"):
        return "  (no news available)"
    lines = []
    for h in news["headlines"][:max_items]:
        lines.append(f"  - [{h['source']}] {h['title'][:120]}")
    return "\n".join(lines)


def _format_multi_tf_block(per_tf_data: dict) -> str:
    """Format each TF's snapshot for the prompt."""
    lines = []
    for tf in TIMEFRAMES:
        data = per_tf_data.get(tf, {})
        if not data:
            lines.append(f"\n[{tf}] No data available")
            continue
        snap = data.get("ta_snapshot", {})
        classical = data.get("classical_ta_score", {})
        lines.append(f"\n[{tf}] (TF weight applies in Python scoring)")
        lines.append(f"  Trend: {snap.get('trend', 'N/A')}")
        lines.append(f"  Price vs EMA21/50/200: {snap.get('above_ema21')}/{snap.get('above_ema50')}/{snap.get('above_ema200')}")
        lines.append(f"  RSI(14): {snap.get('rsi_14', 'N/A')} ({snap.get('rsi_state', 'N/A')})")
        lines.append(f"  MACD: bias={snap.get('macd_bias')}, hist={snap.get('macd_histogram', 0):+.2f}")
        lines.append(f"  Bollinger position: {snap.get('bb_position_pct', 'N/A')}%")
        lines.append(f"  Classical TA score (Python-computed): {classical.get('score', 'N/A')}")
    return "\n".join(lines)


def _clean_json_response(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def call_gemini(prompt: str) -> dict:
    model = genai.GenerativeModel(
        MODEL_NAME,
        generation_config={
            "temperature": 0.1,
            "response_mime_type": "application/json",
        },
    )
    response = model.generate_content(prompt)
    raw = response.text or ""
    clean = _clean_json_response(raw)
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse failed: {e}", "raw_response": raw[:1000]}


def save_signal(verdict: dict, symbol: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    filepath = SIGNALS_DIR / f"{symbol}_multitf_{ts}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(verdict, f, indent=2, default=str)
    return filepath


# ════════════════════════════════════════════════════════════════
# MULTI-TF DATA FETCHING
# ════════════════════════════════════════════════════════════════
def fetch_per_tf_data(symbol: str) -> dict:
    """Fetches OHLCV + indicators for all 6 TFs."""
    cfg = load_config()
    per_tf = {}

    for tf in TIMEFRAMES:
        try:
            validate_interval(tf)
            candle_count = 500 if tf in ("1d", "1w") else 300
            df = fetch_klines(symbol, tf, candle_count)
            df_ind = compute_indicators(df)
            ta_snapshot = summarize_indicators(df_ind)
            classical_ta = compute_classical_ta_score(ta_snapshot)

            per_tf[tf] = {
                "ta_snapshot":         ta_snapshot,
                "classical_ta_score":  classical_ta,
                "atr_14":              ta_snapshot.get("atr_14"),
            }
        except Exception as e:
            print(f"  ⚠️  {tf} failed: {e}")
            per_tf[tf] = {}

    return per_tf


# ════════════════════════════════════════════════════════════════
# MAIN ANALYZE FUNCTION
# ════════════════════════════════════════════════════════════════
def analyze(symbol: str = "BTCUSDT") -> dict:
    """
    Run the full multi-TF analysis pipeline for ONE coin.
    Returns a verdict dict.
    """
    print(f"\n{'='*60}")
    print(f"🧠 MULTI-TF ANALYZER — {symbol}")
    print(f"{'='*60}\n")

    # 1. Fetch live price + funding + context
    print("📊 Fetching live data...")
    price_info = fetch_current_price(symbol)
    funding = fetch_funding_rate(symbol) or 0.0
    context = build_context(symbol, funding_rate=funding, use_fng=True, use_news=True)

    # 2. Fetch per-TF technical snapshots
    print("📈 Fetching all 6 timeframes...")
    per_tf_data = fetch_per_tf_data(symbol)

    # 3. Compute sentiment score (Python, deterministic)
    sentiment_score = compute_sentiment_score(
        context["blended_sentiment"]["blended_score"],
        funding,
    )

    # 4. Load adaptive weights for this coin
    closed_trades = load_closed_trades(symbol)
    methodology_weights = load_adaptive_weights(symbol)

    # 5. Build memory block
    print("🧠 Loading memory...")
    memory_block = build_memory_block(symbol)

    # 6. Build + call Gemini ONCE for the whole multi-TF judgment
    print("📝 Building prompt...")
    template = PROMPT_PATH.read_text(encoding="utf-8")
    multi_tf_block = _format_multi_tf_block(per_tf_data)
    avg_classical = (
        sum(per_tf_data[tf].get("classical_ta_score", {}).get("score", 50) for tf in TIMEFRAMES)
        / len(TIMEFRAMES)
    )
    atr_14_4h = per_tf_data.get("4h", {}).get("atr_14", 0) or 0

    prompt = template.format(
        symbol=symbol,
        current_price=round(price_info["price"], 6),
        change_24h=round(price_info.get("change_24h_pct", 0), 2),
        funding_rate=round(funding * 100, 4),
        atr_14=round(atr_14_4h, 4),
        multi_tf_block=multi_tf_block,
        fng_value=context["fear_greed"]["current_value"],
        fng_label=context["fear_greed"]["current_label"],
        blended_score=context["blended_sentiment"]["blended_score"],
        news_headlines=_format_headlines(context["news"]),
        btc_dominance=context["onchain"]["dominance"].get("btc_dominance_pct", "N/A"),
        mcap_change=context["onchain"]["dominance"].get("market_cap_change_24h_pct", "N/A"),
        long_short_ratio=context["onchain"]["long_short"].get("long_short_ratio", "N/A"),
        trader_bias=context["onchain"]["long_short"].get("trader_bias", "N/A"),
        classical_ta_score=round(avg_classical, 1),
        sentiment_score=sentiment_score,
        memory_block=memory_block,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    print("🤖 Calling Gemini (1 call for all 6 TFs)...")
    ai_response = call_gemini(prompt)

    if "error" in ai_response:
        print(f"❌ AI error: {ai_response['error']}")
        return ai_response

    # 7. PYTHON computes confluence per TF then aggregates
    print("🧮 Computing confluence (Python-driven)...")
    per_tf_scores = ai_response.get("per_tf_scores", {})
    tf_confluences = {}
    per_tf_details = {}

    for tf in TIMEFRAMES:
        tf_ai_scores = per_tf_scores.get(tf, {})
        classical = per_tf_data.get(tf, {}).get("classical_ta_score", {}).get("score", 50)
        ev_calc = compute_ev_edge_score(tf_ai_scores.get("ev_win_prob_pct", 50))

        method_scores = {
            "wyckoff":      tf_ai_scores.get("wyckoff", 50),
            "smc":          tf_ai_scores.get("smc", 50),
            "elliott":      tf_ai_scores.get("elliott", 50),
            "classical_ta": classical,
            "sentiment":    sentiment_score,
            "ev_edge":      ev_calc["score"],
        }

        tf_confluence = compute_tf_confluence(method_scores, methodology_weights)
        tf_confluences[tf] = tf_confluence
        per_tf_details[tf] = {
            "method_scores":  method_scores,
            "tf_confluence":  tf_confluence,
            "ev_R":           ev_calc["ev_R"],
            "win_prob":       ev_calc["win_prob"],
        }

    # 8. Aggregate across timeframes
    aggregate = aggregate_multi_tf_confluence(tf_confluences)
    final_confluence = aggregate["final_confluence"]

    # 9. Calculate final EV from the 4h+1d+1w weighted win prob
    weighted_wp = 0
    weight_sum = 0
    for tf in ("4h", "1d", "1w"):
        wp = per_tf_details.get(tf, {}).get("win_prob", 50)
        w = load_config()["timeframe_weights"].get(tf, 0)
        weighted_wp += wp * w
        weight_sum += w
    final_win_prob = weighted_wp / weight_sum if weight_sum > 0 else 50
    final_ev = compute_ev_edge_score(final_win_prob)

    # 10. Apply decision gates (using 4h profile as primary)
    decision = decide_position(
        final_confluence=final_confluence,
        ev_R=final_ev["ev_R"],
        timeframe="4h",
    )

    # 11. Build final verdict
    current_price = price_info["price"]
    atr_4h = atr_14_4h or current_price * 0.02
    is_long = decision["position"] == "LONG"

    entry_low = round(current_price * 0.998, 6)
    entry_high = round(current_price * 1.002, 6)
    entry_mid = (entry_low + entry_high) / 2

    if is_long:
        stop_loss = round(entry_mid - (1.5 * atr_4h), 6)
        take_profit_1 = round(entry_mid + (3.0 * atr_4h), 6)
        take_profit_2 = round(entry_mid + (6.0 * atr_4h), 6)
    elif decision["position"] == "SHORT":
        stop_loss = round(entry_mid + (1.5 * atr_4h), 6)
        take_profit_1 = round(entry_mid - (3.0 * atr_4h), 6)
        take_profit_2 = round(entry_mid - (6.0 * atr_4h), 6)
    else:
        stop_loss = current_price
        take_profit_1 = current_price
        take_profit_2 = current_price

    verdict = {
        "symbol":            symbol,
        "current_price":     current_price,
        "timestamp":         datetime.now(timezone.utc).isoformat(),
        "position":          decision["position"],
        "confidence":        decision["confidence"],
        "final_confluence":  final_confluence,
        "ev_R":              final_ev["ev_R"],
        "ev_pct":            round(final_ev["ev_R"] * 1.0, 4),
        "ev_positive":       final_ev["ev_R"] > 0,
        "estimated_win_prob_pct": round(final_win_prob, 1),
        "entry_zone":        {"low": entry_low, "high": entry_high},
        "stop_loss":         stop_loss,
        "take_profit_1":     take_profit_1,
        "take_profit_2":     take_profit_2,
        "risk_reward_ratio": 2.0,

        "per_tf_details":    per_tf_details,
        "tf_aggregate":      aggregate,
        "methodology_weights_used": methodology_weights,

        "wyckoff":           ai_response.get("wyckoff", {}),
        "smc":               ai_response.get("smc", {}),
        "elliott_wave":      ai_response.get("elliott_wave", {}),

        "memory_reflection": ai_response.get("memory_reflection", ""),
        "key_catalyst":      ai_response.get("key_catalyst", "none identified"),
        "final_narrative":   ai_response.get("final_narrative", ""),
        "decision_reason":   decision["reason"],
        "gates_used":        decision["gates_used"],
    }

    # 12. Save
    filepath = save_signal(verdict, symbol)
    print(f"💾 Saved: {filepath}")

    # 13. Display summary
    print(f"\n{'─'*60}")
    print(f"🎯 VERDICT — {symbol}")
    print(f"{'─'*60}")
    print(f"   Position:        {verdict['position']} ({verdict['confidence']})")
    print(f"   Final Confluence: {verdict['final_confluence']}%")
    print(f"   EV (R):           {verdict['ev_R']:+.3f}R")
    print(f"   Win Prob:         {verdict['estimated_win_prob_pct']}%")
    print(f"   Entry:            ${entry_low} – ${entry_high}")
    print(f"   SL / TP1 / TP2:   ${stop_loss} / ${take_profit_1} / ${take_profit_2}")
    print(f"   Reason:           {decision['reason']}")
    print(f"{'─'*60}\n")

    return verdict


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-TF AI Crypto Analyzer v4")
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading pair")
    args = parser.parse_args()
    analyze(args.symbol)