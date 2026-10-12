"""Kill test, part 3: does a revenue-growth screen pick different stocks, and earn
different returns, on point-in-time data than on today's restated data?

Each quarter end, rank companies by their latest annual revenue growth and hold
the top N, equally weighted, for the next quarter. The point-in-time screen
uses the revenue figures as they stood on that date; the restated screen uses
today's figures for the same fiscal years.

Writes backtest_quarters.csv and backtest_summary.json to reports/kill-test-full/.
"""

import json
from datetime import date

import numpy as np
import pandas as pd
import yfinance as yf

from groundtruth import parse, sec
from groundtruth.items import ITEMS_BY_NAME

from common import RESULTS, companies, load_facts, statement_histories

REBALANCES = pd.date_range("2021-06-30", "2026-06-30", freq="QE")
TOP_N = (10, 5, 15)  # 10 is the main result; 5 and 15 show how sensitive it is
PRICES = sec.CACHE_DIR.parent / "prices.csv"
BOOTSTRAP_DRAWS = 10_000


def revenue_histories(company: dict) -> dict[date, list[parse.Version]]:
    """Statement-confirmed versions of annual revenue, by fiscal year end."""
    histories = statement_histories(company, load_facts(company), ITEMS_BY_NAME["Revenue"])
    return {end: history for end, (history, found, _) in histories.items() if found}


def growth(histories: dict[date, list[parse.Version]], when: date) -> tuple[float, float] | None:
    """Latest annual revenue growth known on a date: (point-in-time, restated)."""
    known = [end for end, history in histories.items() if parse.as_of(history, when)]
    if not known:
        return None
    current = max(known)
    prior = [end for end in histories if 350 <= (current - end).days <= 380]
    if not prior or not parse.as_of(histories[prior[0]], when):
        return None
    then = (parse.as_of(histories[current], when).val, parse.as_of(histories[prior[0]], when).val)
    now = (histories[current][-1].val, histories[prior[0]][-1].val)
    if then[1] <= 0 or now[1] <= 0:
        return None
    return then[0] / then[1] - 1, now[0] / now[1] - 1


def prices(tickers: list[str]) -> pd.DataFrame:
    if PRICES.exists():
        return pd.read_csv(PRICES, index_col=0, parse_dates=True)
    table = yf.download(tickers, start="2021-06-01", end="2026-10-10", auto_adjust=True, progress=False)["Close"]
    table.to_csv(PRICES)
    return table


def bootstrap_ci(differences: np.ndarray) -> tuple[float, float]:
    """95% confidence interval for the mean, resampling quarters."""
    rng = np.random.default_rng(0)
    means = rng.choice(differences, size=(BOOTSTRAP_DRAWS, len(differences))).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main() -> None:
    universe = companies()
    histories = {c["ticker"]: revenue_histories(c) for c in universe}
    close = prices([c["ticker"] for c in universe]).ffill()

    quarters, growth_rows = [], []
    for start, stop in zip(REBALANCES[:-1], REBALANCES[1:]):
        returns = close.loc[:stop].iloc[-1] / close.loc[:start].iloc[-1] - 1
        signals = {}
        for ticker, history in histories.items():
            pair = growth(history, start.date())
            if pair and not np.isnan(returns[ticker]):
                signals[ticker] = pair
                growth_rows.append({"date": start.date(), "ticker": ticker,
                                    "growth_point_in_time": pair[0], "growth_restated": pair[1]})
        for n in TOP_N:
            picks = [
                set(sorted(signals, key=lambda t: signals[t][k], reverse=True)[:n]) for k in (0, 1)
            ]
            point_in_time, restated = (float(returns[list(p)].mean()) for p in picks)
            quarters.append({
                "top_n": n, "start": start.date(), "end": stop.date(), "companies_ranked": len(signals),
                "return_point_in_time": point_in_time, "return_restated": restated,
                "difference": point_in_time - restated, "picks_in_common": len(picks[0] & picks[1]),
                "only_point_in_time": " ".join(sorted(picks[0] - picks[1])),
                "only_restated": " ".join(sorted(picks[1] - picks[0])),
            })

    quarters = pd.DataFrame(quarters)
    quarters.to_csv(RESULTS / "backtest_quarters.csv", index=False)
    signals = pd.DataFrame(growth_rows)
    gap = (signals.growth_point_in_time - signals.growth_restated).abs()
    summary = {
        "quarters": len(REBALANCES) - 1,
        "growth_observations": len(signals),
        "growth_differs_by_over_1_point": int((gap > 0.01).sum()),
        "growth_differs_by_over_5_points": int((gap > 0.05).sum()),
        "screens": {},
    }
    for n, rows in quarters.groupby("top_n"):
        difference = rows.difference.to_numpy()
        low, high = bootstrap_ci(difference)
        summary["screens"][f"top_{n}"] = {
            "quarters_with_different_picks": int((rows.picks_in_common < n).sum()),
            "mean_quarterly_return_point_in_time": float(rows.return_point_in_time.mean()),
            "mean_quarterly_return_restated": float(rows.return_restated.mean()),
            "mean_quarterly_difference": float(difference.mean()),
            "ci95_low": low, "ci95_high": high,
            "annualized_difference": float(difference.mean() * 4),
            "annualized_ci95": [low * 4, high * 4],
        }
    (RESULTS / "backtest_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
