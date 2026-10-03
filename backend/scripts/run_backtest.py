"""Run the algorithm backtest from the command line and store the report.

    python -m scripts.run_backtest [--days 30] [--max-rounds 3000] [--sim-scale 1]

The report appears on the super admin "Security & Fairness" page, exactly as
if it had been started from there. Prints a short summary.
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.database import close_db, get_session_factory, init_db
from app.services.backtest import run_backtest


async def main(days: int, max_rounds: int, sim_scale: int) -> None:
    await init_db()
    try:
        async with get_session_factory()() as session:
            report = await run_backtest(session, days, max_rounds, sim_scale, actor="cli")
            await session.commit()
    finally:
        await close_db()

    verdict = report["verdict"]
    print(f"Backtest {verdict['status'].upper()} in {report['duration_s']}s: "
          f"{verdict['rounds_replayed']:,} rounds, {verdict['bets_replayed']:,} bets replayed")
    for check in verdict["checks"]:
        print(f"  [{check['status']:>4}] {check['name']}: {check['detail']}")
    for game_id, g in report["replay"]["games"].items():
        if g["rounds"]:
            print(f"  {game_id:<10} rounds {g['rounds']:>6}  bets {g['bets']:>6}  hold {g['actual_hold_pct']}% "
                  f"(expected {g['expected_hold_pct']}%)  issues {len(g['issues'])}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--max-rounds", type=int, default=3000)
    parser.add_argument("--sim-scale", type=int, default=1)
    args = parser.parse_args()
    asyncio.run(main(args.days, args.max_rounds, args.sim_scale))
