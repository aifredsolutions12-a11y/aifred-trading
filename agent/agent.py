"""
Trading AI Agent v2 — Agentic loop with tool use + learning memory.
Replaces the older single-shot ai_analyzer/analyzer.py.

Model: gemini-3.1-flash-lite (stable, cost-effective, supports tool use + JSON)
"""
import os
import re
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
import google.generativeai as genai

from config.config_loader import get_timeframe_config, list_scheduler_targets
from data_collector.chart_data import fetch_klines, fetch_current_price, fetch_funding_rate
from data_collector.indicators import compute_indicators, summarize_indicators
from data_collector.context_builder import build_context
from ai_analyzer.confluence_calculator import count_bullish_bearish, preliminary_confluence
from memory.journal import log_signal
from memory.feedback import build_feedback_block
from memory.weights import load_weights
from utils.api_monitor import monitor
from agent.tools import TOOL_REGISTRY, execute_tool

load_dotenv("config/.env")
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

MODEL_NAME = "gemini-3.1-flash-lite"   # stable GA model, cost-effective
PROMPT_PATH = Path("agent/prompt_agent.txt")
SIGNALS_DIR = Path("data/signals")
SIGNALS_DIR.mkdir(parents=True, exist_ok=True)

MAX_AGENT_STEPS = 4   # max tool calls + 1 final verdict


def _clean_json(text: str) -> str:
    """Strip markdown code fences if Gemini wrapped its JSON."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


@monitor("gemini")
def _call_gemini(prompt: str, temperature: float = 0.2) -> dict:
    """Single Gemini call wrapped in API monitor."""
    model = genai.GenerativeModel(
        MODEL_NAME,
        generation_config={
            "temperature": temperature,
            "response_mime_type": "application/json",
        },
    )
    resp = model.generate_content(prompt)
    return json.loads(_clean_json(resp.text))


def build_observation(symbol: str, timeframe: str) -> dict:
    """Phase 1: gather everything the agent needs to reason about."""
    tf_cfg = get_timeframe_config(symbol, timeframe)
    df = fetch_klines(symbol, timeframe, tf_cfg["candles"])
    df_ind = compute_indicators(df)
    ta = summarize_indicators(df_ind)

    price = fetch_current_price(symbol)
    funding = fetch_funding_rate(symbol) or 0.0
    ctx = build_context(symbol, funding, tf_cfg["use_fng"], tf_cfg["use_news"])

    counts = count_bullish_bearish(ta)
    prelim = preliminary_confluence(counts, ctx["blended_sentiment"]["blended_score"])

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "tf_cfg": tf_cfg,
        "ta": ta,
        "price": price,
        "funding": funding,
        "context": ctx,
        "ta_counts": counts,
        "preliminary": prelim,
        "df_tail": df.tail(20).to_dict(orient="records"),
    }


def run_agent(symbol: str = "BTCUSDT", timeframe: str = "4h") -> dict:
    print(f"\n{'='*60}")
    print(f"AGENT RUN -- {symbol} @ {timeframe}")
    print(f"  model: {MODEL_NAME}")
    print(f"{'='*60}")

    obs = build_observation(symbol, timeframe)
    weights = load_weights()
    feedback = build_feedback_block(symbol, timeframe)

    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    base_prompt = prompt_template.format(
        symbol=symbol,
        timeframe=timeframe,
        observation=json.dumps(
            {k: v for k, v in obs.items() if k != "df_tail"},
            default=str, indent=2,
        ),
        recent_candles=json.dumps(obs["df_tail"], default=str, indent=2),
        weights=json.dumps(weights, indent=2),
        feedback=feedback,
        tool_list=json.dumps(list(TOOL_REGISTRY.keys())),
    )

    # ----- Agentic loop -----
    history = []
    final = None

    for step in range(MAX_AGENT_STEPS):
        print(f"  Step {step + 1}/{MAX_AGENT_STEPS}...")
        step_prompt = base_prompt + "\n\nHISTORY SO FAR:\n" + json.dumps(history, indent=2)
        try:
            resp = _call_gemini(step_prompt)
        except Exception as e:
            print(f"     Gemini call failed: {e}")
            return {"error": str(e), "history": history}

        action = resp.get("action")

        if action == "use_tool":
            tool = resp.get("tool_name")
            args = resp.get("tool_args", {})
            print(f"     Tool call -> {tool}({args})")
            result = execute_tool(tool, args)
            history.append({
                "step": step + 1,
                "tool": tool,
                "args": args,
                "result_summary": str(result)[:500],
            })
            continue

        if action == "final_verdict":
            final = resp.get("verdict")
            break

        # Fallback: unknown action shape -- treat as final
        final = resp
        break

    if final is None:
        final = {
            "error": "Agent exceeded MAX_AGENT_STEPS without a final verdict",
            "history": history,
        }

    final["agent_meta"] = {
        "steps_used": len(history) + 1,
        "tools_called": [h["tool"] for h in history],
        "weights_used": weights,
        "model": MODEL_NAME,
        "run_at": datetime.now(timezone.utc).isoformat(),
    }

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    fpath = SIGNALS_DIR / f"{symbol}_{timeframe}_{ts}.json"
    fpath.write_text(json.dumps(final, indent=2, default=str), encoding="utf-8")
    log_signal(final)
    print(f"  Saved -> {fpath}")
    return final


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=None)
    p.add_argument("--timeframe", default=None)
    p.add_argument("--all-scheduler", action="store_true",
                   help="Run all (symbol, timeframe) pairs where scheduler_active=true")
    args = p.parse_args()

    if args.all_scheduler:
        for sym, tf in list_scheduler_targets():
            try:
                run_agent(sym, tf)
            except Exception as e:
                print(f"FAILED {sym} {tf}: {e}")
    else:
        run_agent(args.symbol or "BTCUSDT", args.timeframe or "4h")
