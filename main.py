"""
Local CLI entrypoint — wraps agent.agent.run_agent.
Usage:
  python main.py --symbol BTCUSDT --timeframe 4h
  python main.py --all
"""
import argparse
from agent.agent import run_agent
from config.config_loader import list_scheduler_targets


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--timeframe", default="4h")
    p.add_argument("--all", action="store_true",
                   help="Run all scheduler-active (symbol, timeframe) pairs")
    args = p.parse_args()

    if args.all:
        for s, tf in list_scheduler_targets():
            try:
                run_agent(s, tf)
            except Exception as e:
                print(f"❌ {s} {tf}: {e}")
    else:
        run_agent(args.symbol, args.timeframe)
