# 🤖 Trading AI Agent v2

An **agentic, self-learning** crypto trading analysis system that runs entirely on free GitHub infrastructure (Actions + Pages) — no server required.

## ✨ Features

- **Agentic loop** — Gemini can request tools (cross-timeframe check, funding lookup, past-signal review, regime stats) before committing to a verdict.
- **Self-learning** — auto-adjusts confluence weights based on rolling win-rate of each analysis method.
- **TP/SL resolver** — independent cron checks Binance candles every 30 min to mark outcomes.
- **Static dashboard** — dark-mode HTML/JS hosted on GitHub Pages, reads JSON committed by Actions.
- **API health monitor** — tracks success/failure/latency of every external call (Binance, CoinGecko, RSS, Gemini).
- **Manual override** — "Run Now" button on dashboard triggers a fresh run via `workflow_dispatch`.

## 🧠 Model

Uses **`gemini-3.1-flash-lite`** — the stable GA cost-effective model that supports tool use, structured JSON output, and high call volume. Estimated cost: **$3–8/month** for ~135 coins × 3 timeframes × 6 runs/day.

## 📁 Folder Structure

```
trading-ai-agent/
├── agent/                      # ⭐ Agentic loop + tools + prompt
│   ├── agent.py
│   ├── tools.py
│   └── prompt_agent.txt
├── memory/                     # ⭐ Learning layer
│   ├── journal.py              # append-only signal log
│   ├── resolver.py             # TP/SL outcome checker
│   ├── stats.py                # win-rate, per-method performance
│   ├── weights.py              # auto-tunes confluence weights
│   └── feedback.py             # injects past performance into next prompt
├── utils/
│   └── api_monitor.py          # tracks every external call
├── data_collector/             # market data (klines, indicators, news, on-chain, sentiment)
├── ai_analyzer/
│   └── confluence_calculator.py
├── config/
│   ├── coins.yaml              # 45-coin watchlist + per-timeframe regime params
│   ├── config_loader.py
│   ├── regime_defaults.py
│   ├── weights.json            # ⭐ auto-tuned weights live here
│   └── .env.example
├── docs/                       # ⭐ GitHub Pages root (dark dashboard)
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── data/                   # JSON written by Actions
├── data/
│   ├── journal.jsonl           # append-only learning log
│   ├── api_health.json
│   └── signals/                # individual run snapshots
├── .github/workflows/
│   ├── agent.yml               # every 4h + manual
│   └── resolver.yml            # every 30 min
├── main.py                     # local CLI
├── export_dashboard.py
├── requirements.txt
└── README.md
```

## 🚀 Setup

### A. Local Run

```bash
git clone https://github.com/YOUR_USER/YOUR_REPO.git
cd YOUR_REPO

python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt

# Add your API key
cp config/.env.example config/.env
# Edit config/.env and paste your GEMINI_API_KEY

# Try a single run
python main.py --symbol BTCUSDT --timeframe 4h

# Try the resolver
python -m memory.resolver

# Build dashboard JSON
python export_dashboard.py
```

### B. Deploy on GitHub

1. **Push to a PUBLIC repo** (public = unlimited free Actions minutes + Pages).

2. **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `GEMINI_API_KEY`
   - Value: your Gemini API key from https://aistudio.google.com/apikey

3. **Settings → Actions → General → Workflow permissions** → select **Read and write permissions** (so the bot can commit back).

4. **Settings → Pages**
   - Source: **Deploy from a branch**
   - Branch: `main`, folder: `/docs`
   - Save.

5. **Trigger the first run**
   - Go to **Actions → "Agent - Run every 4h" → Run workflow**.
   - Wait ~3 min, then visit `https://YOUR_USER.github.io/YOUR_REPO/`.

The dashboard "Run Now" button auto-detects your repo path on GitHub Pages.

## 🔁 How the Learning Loop Works

```
Every 4h        ┌────────────────────────────────────┐
agent.yml ────► │ 1. Build market observation        │
                │ 2. Load auto-tuned weights         │
                │ 3. Load last-10-trade feedback     │
                │ 4. Agentic loop (up to 4 steps,    │
                │    AI can call cross-TF, funding,  │
                │    past-signals, stats tools)      │
                │ 5. Final verdict → journal.jsonl   │
                │ 6. Auto-tune weights (if ≥20 res.) │
                │ 7. Export dashboard JSON           │
                └────────────────────────────────────┘
                          │ commit + push
                          ▼
Every 30 min    ┌────────────────────────────────────┐
resolver.yml ─► │ 1. For each open signal:           │
                │    Walk Binance candles since      │
                │    logged_at → mark TP1/SL hit     │
                │ 2. Update journal.jsonl            │
                │ 3. Export dashboard JSON           │
                └────────────────────────────────────┘
                          │ commit + push
                          ▼
                  📊 GitHub Pages re-serves JSON
```

## ⚙️ Adjusting the Watchlist

Edit `config/coins.yaml`:
- Flip `active: false` on any coin to disable it.
- Add per-coin `timeframe_overrides` to override regime params for specific symbols.
- The `top_tier_symbols` list is reserved for future extra-frequency scheduling.

## 🛡️ API Health

The 🛡️ tab shows status per provider:
- 🟢 < 5% error rate
- 🟡 5–20% error rate
- 🔴 > 20% error rate

Latency and last error are also shown.

## 💰 Cost Notes

With 45 active coins × 3 scheduler-active timeframes (4h/1d/1w) = 135 runs per cycle × 6 cycles/day ≈ 810 runs/day. Each run averages ~2–3 Gemini calls (initial + tool steps).

| Daily Calls | Monthly Cost (gemini-3.1-flash-lite) |
|-------------|--------------------------------------|
| ~2,000      | $3 – $8                              |

Gemini free tier allows 1,500 calls/day, so you'll exceed free → pay-as-you-go. To stay under free tier, set most coins to `active: false` and keep only your top 10.

## 🧯 Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Actions fail with `permission denied to push` | Workflow permissions not set | Settings → Actions → General → Read and write |
| Dashboard empty | First run hasn't finished | Wait for first commit from agent-bot |
| `GEMINI_API_KEY not set` | Secret missing | Settings → Secrets → Actions |
| `Symbol not in watchlist` | Typo or coin disabled | Check `config/coins.yaml` |
| `RuntimeError: ...` in api_health | External API hiccup | Will self-recover; check Health tab |

## 📜 License

MIT — use however you want.
