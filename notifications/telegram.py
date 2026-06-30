"""
Telegram notification module.
Handles: opening report, hourly updates, closure alerts, post-mortem.
"""
import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
PH_TZ = ZoneInfo("Asia/Manila")
UTC_TZ = ZoneInfo("UTC")


def send_telegram(message: str, parse_mode: str = "Markdown") -> bool:
    """Send a message to Telegram. Returns True if successful."""
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ Telegram credentials missing. Preview:")
        print(message[:500])
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            return True
        print(f"⚠️ Telegram error {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        print(f"⚠️ Telegram exception: {e}")
        return False


def is_cycle_start() -> bool:
    """Returns True if current UTC hour is 04 (12 PM PH = cycle start)."""
    return datetime.now(UTC_TZ).hour == 4


def ph_now_str() -> str:
    return datetime.now(PH_TZ).strftime("%d %b %Y, %H:%M PH")


def _fmt_price(v) -> str:
    if v is None:
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if abs(v) >= 1000:
        return f"${v:,.0f}"
    if abs(v) >= 1:
        return f"${v:.4f}"
    if abs(v) >= 0.01:
        return f"${v:.6f}"
    return f"${v:.8f}"


def _emoji_pos(pos: str) -> str:
    return {
        "LONG": "🟢", "SHORT": "🔴",
        "WAIT": "⚪", "HOLD": "🟡", "SKIP": "⚫",
    }.get(pos, "❓")


def _fmt_age(logged_at: str) -> str:
    if not logged_at:
        return "—"
    try:
        opened = datetime.fromisoformat(logged_at.replace("Z", "+00:00"))
        delta = datetime.now(opened.tzinfo) - opened
        hrs = int(delta.total_seconds() // 3600)
        mins = int((delta.total_seconds() % 3600) // 60)
        if hrs >= 24:
            return f"{hrs // 24}d {hrs % 24}h"
        if hrs > 0:
            return f"{hrs}h {mins}m"
        return f"{mins}m"
    except Exception:
        return "—"


def _escape_md(text: str) -> str:
    """Escape Telegram markdown special chars."""
    if not text:
        return ""
    for ch in ["_", "*", "[", "]", "`"]:
        text = text.replace(ch, f"\\{ch}")
    return text


# ════════════════════════════════════════════════════════════
# ALERT 1: OPENING REPORT (12 PM PH or manual)
# ════════════════════════════════════════════════════════════
def send_opening_report(
    active_positions: List[Dict],
    new_signals: List[Dict],
    waiting_coins: List[str],
    yesterday_summary: Dict,
    dashboard_url: str = "",
) -> bool:
    lines = [
        "🌅 *DAILY TRADING BRIEF*",
        f"📅 {ph_now_str()}",
    ]

    # Active positions
    if active_positions:
        lines.append(f"\n*━━━ ACTIVE POSITIONS ({len(active_positions)}) ━━━*")
        for p in active_positions:
            emoji = _emoji_pos(p.get("position"))
            sym = p.get("symbol", "?")
            pos = p.get("position", "?")
            conf = p.get("confidence", "?")
            ez = p.get("entry_zone", {})
            sl = p.get("stop_loss")
            tp1 = p.get("take_profit_1")
            ev = float(p.get("_latest_ev_R") or p.get("ev_R") or 0)
            age = _fmt_age(p.get("logged_at"))
            refresh = p.get("_refresh_count", 0)

            orig_conf = p.get("confidence")
            latest_conf = p.get("_latest_confidence") or orig_conf
            shift = ""
            if orig_conf != latest_conf:
                shift = f"\n   ⚠️ Conviction shift: {orig_conf}→{latest_conf}"

            lines.append(
                f"\n{emoji} *{sym}* │ {pos} ({conf})\n"
                f"   Entry: {_fmt_price(ez.get('low'))}–{_fmt_price(ez.get('high'))}\n"
                f"   SL: {_fmt_price(sl)} │ TP1: {_fmt_price(tp1)}\n"
                f"   Age: {age} │ Refreshes: {refresh} │ EV: {ev:+.2f}R{shift}"
            )
    else:
        lines.append("\n*━━━ NO ACTIVE POSITIONS ━━━*")

    # New signals
    if new_signals:
        lines.append(f"\n*━━━ NEW SIGNALS ({len(new_signals)}) ━━━*")
        for s in new_signals:
            emoji = _emoji_pos(s.get("position"))
            sym = s.get("symbol", "?")
            pos = s.get("position", "?")
            conf = s.get("confidence", "?")
            ez = s.get("entry_zone", {})
            sl = s.get("stop_loss")
            tp1 = s.get("take_profit_1")
            ev = float(s.get("ev_R", 0))
            wp = s.get("estimated_win_prob_pct", 0)
            wyckoff = s.get("wyckoff", {}).get("phase", "—")

            lines.append(
                f"\n🆕 *{sym}* │ {pos} ({conf})\n"
                f"   Entry: {_fmt_price(ez.get('low'))}–{_fmt_price(ez.get('high'))}\n"
                f"   SL: {_fmt_price(sl)} │ TP1: {_fmt_price(tp1)}\n"
                f"   EV: {ev:+.2f}R │ WP: {wp}% │ Wyckoff: {wyckoff}"
            )

    # Waiting list
    if waiting_coins:
        lines.append(f"\n*━━━ WAITING ({len(waiting_coins)}) ━━━*")
        # Show as comma-separated, max 50 chars per line
        coin_str = ", ".join(waiting_coins)
        lines.append(coin_str)

    # Yesterday summary
    if yesterday_summary and yesterday_summary.get("closed_count", 0) > 0:
        lines.append("\n*━━━ YESTERDAY ━━━*")
        ys = yesterday_summary
        lines.append(
            f"Closed: {ys.get('closed_count', 0)} │ "
            f"{ys.get('wins', 0)}W / {ys.get('losses', 0)}L │ "
            f"WR: {ys.get('win_rate', 0):.0f}%\n"
            f"Net PnL: {ys.get('total_pnl_R', 0):+.2f}R"
        )

    if dashboard_url:
        lines.append(f"\n📊 [Dashboard]({dashboard_url})")

    lines.append(f"\n⏱️ Next run in 1 hour")

    return send_telegram("\n".join(lines))


# ════════════════════════════════════════════════════════════
# ALERT 2: HOURLY UPDATE (compact, "what changed")
# ════════════════════════════════════════════════════════════
def send_hourly_update(
    unchanged: List[Dict],
    attention_needed: List[Dict],
    new_opens: List[Dict],
    flipped: List[Dict],
    run_number: int,
    dashboard_url: str = "",
) -> bool:
    lines = [
        f"🔄 *HOURLY UPDATE* — Run #{run_number}/24",
        f"📅 {ph_now_str()}",
    ]

    # Things needing attention (most important — show first)
    if attention_needed:
        lines.append(f"\n*━━━ ⚠️ ATTENTION ({len(attention_needed)}) ━━━*")
        for a in attention_needed:
            sym = a.get("symbol", "?")
            reason = a.get("reason", "shift detected")
            old = a.get("old", "?")
            new = a.get("new", "?")
            suggestion = a.get("suggestion", "")
            lines.append(
                f"\n⚠️ *{sym}*: {reason}\n"
                f"   Was: {old} → Now: {new}\n"
                f"   💡 {suggestion}"
            )

    # Flipped positions
    if flipped:
        lines.append(f"\n*━━━ 🔄 FLIPPED ({len(flipped)}) ━━━*")
        for f in flipped:
            sym = f.get("symbol", "?")
            old_dir = f.get("old_direction", "?")
            new_dir = f.get("new_direction", "?")
            age = f.get("age", "?")
            lines.append(
                f"🔄 *{sym}*: {old_dir} ({age}) → {new_dir}"
            )

    # New opens
    if new_opens:
        lines.append(f"\n*━━━ 🆕 NEW POSITIONS ({len(new_opens)}) ━━━*")
        for n in new_opens:
            emoji = _emoji_pos(n.get("position"))
            sym = n.get("symbol", "?")
            pos = n.get("position", "?")
            conf = n.get("confidence", "?")
            ev = float(n.get("ev_R", 0))
            lines.append(
                f"{emoji} *{sym}* │ {pos} ({conf}) │ EV: {ev:+.2f}R"
            )

    # Unchanged (compact list)
    if unchanged:
        symbols_only = []
        for u in unchanged:
            sym = u.get("symbol", "?")
            pos = u.get("position", "?")
            refresh = u.get("_refresh_count", 0)
            emoji = _emoji_pos(pos)
            symbols_only.append(f"{emoji}{sym}({refresh}×)")
        lines.append(f"\n*━━━ ✅ UNCHANGED ({len(unchanged)}) ━━━*")
        # 4 per line
        for i in range(0, len(symbols_only), 4):
            lines.append(" ".join(symbols_only[i:i+4]))

    # Nothing happened
    if not (attention_needed or flipped or new_opens or unchanged):
        lines.append("\n💤 No active positions or new signals")

    if dashboard_url:
        lines.append(f"\n📊 [Dashboard]({dashboard_url})")

    return send_telegram("\n".join(lines))


# ════════════════════════════════════════════════════════════
# ALERT 3: TRADE CLOSED (from resolver)
# ════════════════════════════════════════════════════════════
def send_closure_alert(trade: Dict) -> bool:
    outcome = trade.get("outcome", "?")
    sym = trade.get("symbol", "?")
    pos = trade.get("position", "?")
    pnl = float(trade.get("pnl_pct", 0))

    emoji = "✅" if outcome == "TP1" else "🛑" if outcome == "SL" else "⏰"
    
    msg = (
        f"{emoji} *{outcome} HIT — {sym}*\n"
        f"{pos} closed │ PnL: {pnl:+.2f}%\n"
        f"Logged: {_fmt_age(trade.get('logged_at'))} ago"
    )
    return send_telegram(msg)


# ════════════════════════════════════════════════════════════
# ALERT 4: POST-MORTEM (end of cycle, 11 AM PH)
# ════════════════════════════════════════════════════════════
def send_postmortem_report(
    closed_today: List[Dict],
    still_open: List[Dict],
    ai_lessons: List[Dict],
    weekly_stats: Dict = None,
) -> bool:
    lines = [
        "🌙 *DAY CLOSED — End of Cycle*",
        f"📅 {ph_now_str()}",
    ]

    # Closed trades
    if closed_today:
        wins = sum(1 for t in closed_today if t.get("outcome") == "TP1")
        losses = sum(1 for t in closed_today if t.get("outcome") == "SL")
        total_pnl = sum(float(t.get("pnl_pct", 0)) for t in closed_today)
        wr = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

        lines.append(f"\n*━━━ TRADES CLOSED ({len(closed_today)}) ━━━*")
        for t in closed_today:
            outcome = t.get("outcome", "?")
            icon = "✅" if outcome == "TP1" else "🛑"
            sym = t.get("symbol", "?")
            pos = t.get("position", "?")
            pnl = float(t.get("pnl_pct", 0))
            lines.append(f"{icon} {sym} {pos} → {outcome} ({pnl:+.2f}%)")

        lines.append(f"\n*Day Total:* {total_pnl:+.2f}% │ {wins}W/{losses}L (WR: {wr:.0f}%)")

    # Still open
    if still_open:
        lines.append(f"\n*━━━ STILL OPEN ({len(still_open)}) ━━━*")
        for p in still_open:
            emoji = _emoji_pos(p.get("position"))
            sym = p.get("symbol", "?")
            pos = p.get("position", "?")
            age = _fmt_age(p.get("logged_at"))
            refresh = p.get("_refresh_count", 0)
            lines.append(f"{emoji} {sym} {pos} │ {age} │ {refresh}× refreshes")

    # AI lessons
    if ai_lessons:
        lines.append(f"\n*━━━ 💡 AI LESSONS ━━━*")
        for lesson in ai_lessons[:3]:  # max 3
            coin = lesson.get("coin", "?")
            text = lesson.get("lesson", "")[:200]
            lines.append(f"\n*{coin}*: _{text}_")

    # Weekly stats
    if weekly_stats:
        lines.append(f"\n*━━━ WEEK TO DATE ━━━*")
        lines.append(
            f"Trades: {weekly_stats.get('total', 0)} │ "
            f"{weekly_stats.get('wins', 0)}W / {weekly_stats.get('losses', 0)}L\n"
            f"PnL: {weekly_stats.get('total_pnl_pct', 0):+.2f}%"
        )

    lines.append(f"\n🌅 *Next cycle starts at 12:00 PM PH*")
    return send_telegram("\n".join(lines))


# ════════════════════════════════════════════════════════════
# ALERT 3: TRADE CLOSED (from resolver) — v3 with BE + Time-out
# ════════════════════════════════════════════════════════════
def send_closure_alert(trade: Dict) -> bool:
    outcome = trade.get("outcome", "?")
    sym = trade.get("symbol", "?")
    pos = trade.get("position", "?")
    pnl = float(trade.get("pnl_pct", 0))
    pnl_R = trade.get("pnl_R")

    icon_map = {
        "TP_HIT":    ("✅", "TAKE PROFIT HIT"),
        "TP1":       ("✅", "TAKE PROFIT HIT"),
        "SL":        ("🛑", "STOP LOSS HIT"),
        "BE_STOP":   ("🟦", "BREAK-EVEN STOP — Trade exited flat (BE was armed)"),
        "TIME_WIN":  ("⏰✅", "TIME-OUT WIN — Force-closed in profit"),
        "TIME_LOSS": ("⏰🛑", "TIME-OUT LOSS — Force-closed in loss"),
        "TIME_FLAT": ("⏰⚪", "TIME-OUT FLAT — Force-closed near breakeven"),
    }
    icon, label = icon_map.get(outcome, ("❓", outcome))

    pnl_R_str = f" ({pnl_R:+.2f}R)" if isinstance(pnl_R, (int, float)) else ""

    msg = (
        f"{icon} *{label} — {sym}*\n"
        f"{pos} closed │ PnL: {pnl:+.2f}%{pnl_R_str}\n"
        f"Logged: {_fmt_age(trade.get('logged_at'))} ago"
    )

    # Add BE context if relevant
    if trade.get("be_activated") and outcome != "BE_STOP":
        msg += f"\n🟦 BE was armed during trade"

    note = trade.get("outcome_note")
    if note:
        msg += f"\n💬 {note}"

    return send_telegram(msg)


# Add this NEW alert function for BE arming (called from resolver workflow)
def send_be_armed_alert(trade: Dict) -> bool:
    sym = trade.get("symbol", "?")
    pos = trade.get("position", "?")
    entry_mid = trade.get("entry_zone", {})
    age = _fmt_age(trade.get("logged_at"))

    msg = (
        f"🟦 *BREAK-EVEN ARMED — {sym}*\n"
        f"{pos} │ Stop moved to entry\n"
        f"Age: {age} │ Risk-free from here ✅"
    )
    return send_telegram(msg)
