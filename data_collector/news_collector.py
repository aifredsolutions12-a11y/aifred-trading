"""
Crypto news RSS collector.
"""
import feedparser
from datetime import datetime, timezone, timedelta

RSS_FEEDS = {
    "CoinDesk":      "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
    "BitcoinMag":    "https://bitcoinmagazine.com/.rss/full/",
    "Decrypt":       "https://decrypt.co/feed",
}

BTC_KEYWORDS = [
    "bitcoin", "btc", "crypto", "ethereum", "eth", "spot etf",
    "halving", "miner", "hashrate", "sec", "regulation", "fed",
    "interest rate", "cpi", "inflation", "altcoin",
]


def _is_relevant(text: str) -> bool:
    text_lower = (text or "").lower()
    return any(kw in text_lower for kw in BTC_KEYWORDS)


def _parse_date(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        val = entry.get(key)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def fetch_news(max_per_source: int = 10, hours_back: int = 48) -> dict:
    """Aggregate recent crypto headlines."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    headlines = []
    stats = {}

    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            kept = 0
            for entry in feed.entries[:max_per_source * 3]:
                title = entry.get("title", "")
                if not _is_relevant(title):
                    continue
                published = _parse_date(entry)
                if published and published < cutoff:
                    continue
                headlines.append({
                    "source": source,
                    "title": title,
                    "link": entry.get("link", ""),
                    "published": published.isoformat() if published else None,
                })
                kept += 1
                if kept >= max_per_source:
                    break
            stats[source] = {"fetched": len(feed.entries), "kept": kept, "ok": True}
        except Exception as e:
            stats[source] = {"error": str(e), "ok": False}

    headlines.sort(key=lambda x: x["published"] or "", reverse=True)
    return {"count": len(headlines), "headlines": headlines, "sources_stats": stats}
