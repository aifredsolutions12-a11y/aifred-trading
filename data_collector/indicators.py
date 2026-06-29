"""
Technical indicators using the `ta` library.
"""
import pandas as pd
import numpy as np
import ta


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add a standard set of indicators to an OHLCV DataFrame."""
    df = df.copy()
    close = df["close"]
    high, low = df["high"], df["low"]

    # EMAs
    df["EMA_9"]   = ta.trend.EMAIndicator(close, window=9).ema_indicator()
    df["EMA_21"]  = ta.trend.EMAIndicator(close, window=21).ema_indicator()
    df["EMA_50"]  = ta.trend.EMAIndicator(close, window=50).ema_indicator()
    df["EMA_200"] = ta.trend.EMAIndicator(close, window=200).ema_indicator()

    # RSI
    df["RSI_14"] = ta.momentum.RSIIndicator(close, window=14).rsi()

    # MACD
    macd = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
    df["MACD"]        = macd.macd()
    df["MACD_signal"] = macd.macd_signal()
    df["MACD_hist"]   = macd.macd_diff()

    # Bollinger Bands
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    df["BB_upper"]  = bb.bollinger_hband()
    df["BB_middle"] = bb.bollinger_mavg()
    df["BB_lower"]  = bb.bollinger_lband()

    # ATR
    df["ATR_14"] = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range()

    # OBV
    df["OBV"] = ta.volume.OnBalanceVolumeIndicator(close, df["volume"]).on_balance_volume()

    return df


def summarize_indicators(df: pd.DataFrame) -> dict:
    """Build a compact LLM-friendly summary of the latest indicator state."""
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    rsi = float(last["RSI_14"]) if pd.notna(last["RSI_14"]) else 50.0
    macd_hist = float(last["MACD_hist"]) if pd.notna(last["MACD_hist"]) else 0.0
    prev_hist = float(prev["MACD_hist"]) if pd.notna(prev["MACD_hist"]) else 0.0

    close = float(last["close"])
    ema50 = float(last["EMA_50"]) if pd.notna(last["EMA_50"]) else close
    ema200 = float(last["EMA_200"]) if pd.notna(last["EMA_200"]) else close
    bb_u = float(last["BB_upper"]) if pd.notna(last["BB_upper"]) else close
    bb_l = float(last["BB_lower"]) if pd.notna(last["BB_lower"]) else close
    bb_range = max(bb_u - bb_l, 1e-9)
    bb_pos_pct = round((close - bb_l) / bb_range * 100, 1)

    atr = float(last["ATR_14"]) if pd.notna(last["ATR_14"]) else 0.0
    vol_pct = round((atr / close) * 100, 2) if close else 0.0

    return {
        "timestamp": str(last["timestamp"]),
        "close": close,
        "trend": "BULLISH (EMA50 > EMA200)" if ema50 > ema200 else "BEARISH (EMA50 < EMA200)",
        "ema_9":  float(last["EMA_9"])  if pd.notna(last["EMA_9"])  else None,
        "ema_21": float(last["EMA_21"]) if pd.notna(last["EMA_21"]) else None,
        "ema_50": ema50,
        "ema_200": ema200,
        "rsi_14": round(rsi, 2),
        "rsi_state": "Oversold" if rsi < 30 else "Overbought" if rsi > 70 else "Neutral",
        "macd":           float(last["MACD"])        if pd.notna(last["MACD"])        else 0.0,
        "macd_signal":    float(last["MACD_signal"]) if pd.notna(last["MACD_signal"]) else 0.0,
        "macd_histogram": macd_hist,
        "macd_bias": "Bullish" if macd_hist > 0 else "Bearish",
        "macd_fresh_cross": bool((macd_hist > 0 and prev_hist <= 0) or (macd_hist < 0 and prev_hist >= 0)),
        "bb_upper": bb_u,
        "bb_middle": float(last["BB_middle"]) if pd.notna(last["BB_middle"]) else close,
        "bb_lower": bb_l,
        "bb_position_pct": bb_pos_pct,
        "atr_14": atr,
        "volatility_pct": vol_pct,
        "obv": float(last["OBV"]) if pd.notna(last["OBV"]) else 0.0,
        "above_ema21":  bool(close > (float(last["EMA_21"])  if pd.notna(last["EMA_21"])  else close)),
        "above_ema50":  bool(close > ema50),
        "above_ema200": bool(close > ema200),
    }
