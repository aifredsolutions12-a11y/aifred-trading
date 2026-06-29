"""
Blends sentiment, news, funding, and on-chain into a single context dict.
"""
from data_collector.sentiment_collector import fetch_fear_greed
from data_collector.news_collector import fetch_news
from data_collector.onchain_collector import fetch_onchain_snapshot


def _funding_score(funding_rate: float | None) -> float:
    """Normalize funding into a -1..+1 contrarian sentiment score."""
    if funding_rate is None:
        return 0.0
    if funding_rate > 0.0005:   return -0.6   # very long-heavy → contrarian bearish
    if funding_rate > 0.0002:   return -0.3
    if funding_rate < -0.0005:  return 0.6
    if funding_rate < -0.0002:  return 0.3
    return 0.0


def _fng_score(fng: dict) -> float:
    """Normalize F&G value (0-100) into a -1..+1 contrarian score."""
    v = fng.get("current_value", 50)
    # extreme fear = bullish (+1), extreme greed = bearish (-1)
    return round((50 - v) / 50.0, 3)


def _news_score(news: dict) -> float:
    """Cheap keyword polarity of recent headlines (-1..+1)."""
    headlines = news.get("headlines", [])
    if not headlines:
        return 0.0
    BULL = ("rally", "surge", "high", "approves", "bullish", "buy", "etf", "adoption", "soar")
    BEAR = ("crash", "drop", "ban", "hack", "sell-off", "bearish", "lawsuit", "down", "plunge")
    score = 0
    for h in headlines:
        t = h["title"].lower()
        if any(w in t for w in BULL): score += 1
        if any(w in t for w in BEAR): score -= 1
    return max(-1.0, min(1.0, score / max(len(headlines), 1)))


def build_blended_sentiment_score(fng: dict, news: dict, funding_rate: float | None,
                                  use_fng: bool, use_news: bool) -> dict:
    """Weighted blend → -1 (bearish) to +1 (bullish)."""
    fng_s     = _fng_score(fng) if use_fng else 0.0
    news_s    = _news_score(news) if use_news else 0.0
    funding_s = _funding_score(funding_rate)

    # Weights re-normalized based on what's enabled
    weights = {"fng": 0.50 if use_fng else 0.0,
               "news": 0.35 if use_news else 0.0,
               "funding": 0.15}
    total_w = sum(weights.values()) or 1.0
    weights = {k: v / total_w for k, v in weights.items()}

    blended = round(fng_s * weights["fng"] + news_s * weights["news"] + funding_s * weights["funding"], 3)

    if blended >= 0.3:    label = "Bullish"
    elif blended >= 0.1:  label = "Mildly Bullish"
    elif blended <= -0.3: label = "Bearish"
    elif blended <= -0.1: label = "Mildly Bearish"
    else:                 label = "Neutral"

    return {
        "blended_score": blended,
        "blended_label": label,
        "components": {"fng": fng_s, "news": news_s, "funding": funding_s},
        "weights": weights,
    }


def build_context(symbol: str, funding_rate: float | None,
                  use_fng: bool = True, use_news: bool = True) -> dict:
    """Full context for downstream agent reasoning."""
    fng = fetch_fear_greed() if use_fng else {"current_value": 50, "current_label": "skipped"}
    news = fetch_news() if use_news else {"count": 0, "headlines": []}
    onchain = fetch_onchain_snapshot(symbol)

    blended = build_blended_sentiment_score(fng, news, funding_rate, use_fng, use_news)

    return {
        "symbol": symbol,
        "fear_greed": fng,
        "news": news,
        "onchain": onchain,
        "funding_rate": funding_rate,
        "blended_sentiment": blended,
    }
