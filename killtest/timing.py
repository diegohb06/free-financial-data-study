"""Timing look-ahead test on current S&P 500 members, with quarterly data.

Two versions of the same screens, using identical numbers and differing only
in when each quarter's results are treated as known:

  period-end  on the fiscal period end date (what a table keyed by period date implies)
  filing-date on the date the 10-Q or 10-K was actually filed with the SEC

Screens: trailing-twelve-month revenue growth, and earnings yield (trailing
net income over market value). Each rebalance date, hold the top fifth of the
ranked companies, equally weighted, until the next one.

Writes timing_quarters.csv and timing_summary.json to reports/kill-test-timing/.
"""

import csv
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from groundtruth import quarterly, sec
from groundtruth.items import BANK_REVENUE_TAGS, ITEMS_BY_NAME

from backtest import bootstrap_ci

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "reports" / "kill-test-timing"
CACHE = sec.CACHE_DIR.parent
FIRST_REBALANCE, LAST_REBALANCE = "2012-03-31", "2026-06-30"
OFFSETS = (0, 1, 2)  # months after each calendar quarter end; 0 is the main test
SCREENS = ("revenue_growth", "earnings_yield")
# A figure older than this on the rebalance date is too stale to rank on.
MAX_AGE = {"period_end": 135, "filing_date": 225}


def members() -> list[dict]:
    """Current S&P 500 members, one row per company (extra share classes dropped)."""
    seen, rows = set(), []
    with open(HERE / "sp500.csv") as handle:
        for row in csv.DictReader(handle):
            if row["cik"] not in seen:
                seen.add(row["cik"])
                rows.append(row)
    return rows


def company_quarters(member: dict) -> list[dict]:
    is_bank = member["sub_industry"].endswith("Banks")
    tags = BANK_REVENUE_TAGS if is_bank else ITEMS_BY_NAME["Revenue"].tags
    try:
        facts = sec.company_facts(int(member["cik"]))
    except Exception:
        return []
    return [
        {"ticker": member["ticker"], "end": q.end, "filed": q.filed, "form": q.form,
         "revenue_ttm": q.revenue_ttm, "net_income_ttm": q.net_income_ttm, "shares": q.shares}
        for q in quarterly.quarters(facts, tags)
    ]


def fundamentals() -> pd.DataFrame:
    """Every company's quarters with trailing figures and filing dates."""
    path = CACHE / "timing_quarters.csv"
    if path.exists():
        return pd.read_csv(path, parse_dates=["end", "filed"])
    with ThreadPoolExecutor(8) as pool:
        rows = [row for company in pool.map(company_quarters, members()) for row in company]
    table = pd.DataFrame(rows)
    table.to_csv(path, index=False)
    return pd.read_csv(path, parse_dates=["end", "filed"])


def prices(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Daily close (split-adjusted), total-return close, and split ratios."""
    path = CACHE / "timing_prices.pkl"
    if path.exists():
        return pd.read_pickle(path)
    yahoo = [t.replace(".", "-") for t in tickers]
    raw = yf.download(yahoo, start="2011-12-01", end="2026-10-10", auto_adjust=False, actions=True, progress=False)
    tables = {
        name: raw[column].rename(columns=dict(zip(yahoo, tickers)))
        for name, column in (("close", "Close"), ("total_return", "Adj Close"), ("splits", "Stock Splits"))
    }
    pd.to_pickle(tables, path)
    return tables


def add_signals(table: pd.DataFrame, splits: pd.DataFrame) -> pd.DataFrame:
    """Revenue growth against the same quarter a year earlier, and shares on today's share basis."""
    table = table[(table.filed > table.end) & ((table.filed - table.end).dt.days <= 180)].copy()
    table = table.sort_values(["ticker", "end"])
    year_ago = table[["ticker", "end", "revenue_ttm"]].rename(columns={"end": "prior_end", "revenue_ttm": "prior_revenue"})
    table["target"] = table.end - pd.Timedelta(days=365)
    matched = pd.merge_asof(
        table.sort_values("target"), year_ago.sort_values("prior_end"),
        left_on="target", right_on="prior_end", by="ticker",
        direction="nearest", tolerance=pd.Timedelta(days=15),
    )
    matched["revenue_growth"] = np.where(
        matched.prior_revenue > 0, matched.revenue_ttm / matched.prior_revenue - 1, np.nan
    )

    # Shares are reported on the share basis of the filing date; prices are
    # adjusted for every split since. Restate shares for splits after filing.
    def later_splits(row) -> float:
        if row.ticker not in splits.columns:
            return np.nan
        ratios = splits.loc[splits.index > row.filed, row.ticker]
        return float(ratios[ratios > 0].prod())

    matched["shares_today_basis"] = matched.shares * matched.apply(later_splits, axis=1)
    return matched.drop(columns=["target", "prior_end", "prior_revenue"]).sort_values(["ticker", "end"])


def known(table: pd.DataFrame, when: pd.Timestamp, version: str) -> pd.DataFrame:
    """Each company's latest quarter under one version's idea of what is known on a date."""
    available = table[(table.end if version == "period_end" else table.filed) <= when]
    latest = available.sort_values("end").groupby("ticker").tail(1)
    fresh = (when - latest.end).dt.days <= MAX_AGE[version]
    return latest[fresh].set_index("ticker")


def rebalance_dates(offset: int) -> pd.DatetimeIndex:
    return pd.date_range(FIRST_REBALANCE, LAST_REBALANCE, freq="QE") + pd.DateOffset(months=offset)


def run(table: pd.DataFrame, close: pd.DataFrame, total_return: pd.DataFrame, offset: int) -> list[dict]:
    dates = rebalance_dates(offset)
    rows = []
    for start, stop in zip(dates[:-1], dates[1:]):
        price = close.loc[:start].iloc[-1]
        returns = total_return.loc[:stop].iloc[-1] / total_return.loc[:start].iloc[-1] - 1
        views = {}
        for version in MAX_AGE:
            view = known(table, start, version)
            view["earnings_yield"] = view.net_income_ttm / (view.shares_today_basis * price.reindex(view.index))
            views[version] = view
        for screen in SCREENS:
            signals = {v: views[v][screen].replace([np.inf, -np.inf], np.nan).dropna() for v in views}
            # Rank the same companies in both versions, so only the timing differs.
            both = signals["period_end"].index.intersection(signals["filing_date"].index)
            both = both.intersection(returns.dropna().index)
            if len(both) < 50:
                continue
            size = len(both) // 5
            row = {"offset_months": offset, "screen": screen, "start": start.date(),
                   "end": stop.date(), "companies_ranked": len(both)}
            picks = {}
            for version, signal in signals.items():
                ranked = signal[both].sort_values(ascending=False)
                picks[version] = set(ranked.index[:size])
                row[f"top_{version}"] = float(returns[ranked.index[:size]].mean())
                row[f"long_short_{version}"] = row[f"top_{version}"] - float(returns[ranked.index[-size:]].mean())
            row["top_difference"] = row["top_period_end"] - row["top_filing_date"]
            row["long_short_difference"] = row["long_short_period_end"] - row["long_short_filing_date"]
            row["share_of_picks_in_common"] = len(picks["period_end"] & picks["filing_date"]) / size
            row["signals_that_differ"] = float(
                (signals["period_end"][both] != signals["filing_date"][both]).mean()
            )
            rows.append(row)
    return rows


def detectable(differences: np.ndarray) -> float:
    """Smallest true mean this many observations would detect 80% of the time at the 5% level."""
    return float((1.96 + 0.84) * differences.std(ddof=1) / np.sqrt(len(differences)))


def describe(differences: np.ndarray) -> dict:
    """Annualized mean, confidence interval and power for a series of quarterly differences."""
    low, high = bootstrap_ci(differences)
    standard_error = differences.std(ddof=1) / np.sqrt(len(differences))
    return {
        "quarters": len(differences),
        "annualized_difference": float(differences.mean() * 4),
        "annualized_ci95": [low * 4, high * 4],
        "t_statistic": float(differences.mean() / standard_error) if standard_error else 0.0,
        "share_of_quarters_period_end_ahead": float((differences > 0).mean()),
        "annualized_detectable_effect_80pct_power": detectable(differences) * 4,
    }


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    raw = fundamentals()
    market = prices(sorted(raw.ticker.unique()))
    table = add_signals(raw, market["splits"])
    close, total_return = market["close"].ffill(), market["total_return"].ffill()

    quarters = pd.DataFrame([row for offset in OFFSETS for row in run(table, close, total_return, offset)])
    quarters.to_csv(RESULTS / "timing_quarters.csv", index=False)

    lag = (table.filed - table.end).dt.days
    summary = {
        "companies_in_index_list": len(members()),
        "companies_with_usable_quarters": int(table.dropna(subset=["revenue_ttm", "net_income_ttm"]).ticker.nunique()),
        "company_quarters": len(table),
        "filing_lag_days": {"median": float(lag.median()), "p10": float(lag.quantile(0.1)), "p90": float(lag.quantile(0.9))},
        "tests": {},
    }
    for (offset, screen), rows in quarters.groupby(["offset_months", "screen"]):
        summary["tests"][f"{screen}_offset_{offset}m"] = {
            "first_rebalance": str(rows.start.min()), "last_rebalance": str(rows.start.max()),
            "average_companies_ranked": float(rows.companies_ranked.mean()),
            "average_share_of_picks_in_common": float(rows.share_of_picks_in_common.mean()),
            "average_share_of_signals_that_differ": float(rows.signals_that_differ.mean()),
            "annualized_return_period_end": float(rows.top_period_end.mean() * 4),
            "annualized_return_filing_date": float(rows.top_filing_date.mean() * 4),
            "top_fifth": describe(rows.top_difference.to_numpy()),
            "long_short": describe(rows.long_short_difference.to_numpy()),
        }
    # Robustness of the main test (rebalancing on calendar quarter ends).
    main_test = quarters[quarters.offset_months == 0]
    veterans = {m["ticker"] for m in members() if m["date_added"] <= FIRST_REBALANCE}
    veteran_rows = pd.DataFrame(run(table[table.ticker.isin(veterans)], close, total_return, 0))
    summary["robustness"] = {"companies_in_index_since_before_first_rebalance": len(veterans)}
    for screen in SCREENS:
        rows = main_test[main_test.screen == screen].sort_values("start")
        half = len(rows) // 2
        summary["robustness"][screen] = {
            "first_half_top_fifth": describe(rows.top_difference.to_numpy()[:half]),
            "second_half_top_fifth": describe(rows.top_difference.to_numpy()[half:]),
            "long_standing_members_top_fifth": describe(
                veteran_rows[veteran_rows.screen == screen].top_difference.to_numpy()
            ),
            "long_standing_members_long_short": describe(
                veteran_rows[veteran_rows.screen == screen].long_short_difference.to_numpy()
            ),
        }
    (RESULTS / "timing_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
