"""Tests for trailing-twelve-month figures and the timing test's idea of "known"."""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "killtest"))

import timing  # noqa: E402
from groundtruth import quarterly, sec  # noqa: E402
from groundtruth.items import ITEMS_BY_NAME  # noqa: E402

REVENUE_TAGS = ("Revenues",)


def fact(start, end, val, accn, filed, form):
    return {"start": start, "end": end, "val": val, "accn": accn, "filed": filed, "form": form}


def company():
    """Fiscal 2021 revenue 400; first half of 2022 is 260 against 180 a year earlier."""
    revenue = [
        fact("2021-01-01", "2021-12-31", 400, "K-21", "2022-02-20", "10-K"),
        fact("2021-10-01", "2021-12-31", 120, "K-21", "2022-02-20", "10-K"),
        # Second-quarter report: the quarter and the half year, each with last year's.
        fact("2022-04-01", "2022-06-30", 140, "Q2-22", "2022-08-05", "10-Q"),
        fact("2021-04-01", "2021-06-30", 95, "Q2-22", "2022-08-05", "10-Q"),
        fact("2022-01-01", "2022-06-30", 260, "Q2-22", "2022-08-05", "10-Q"),
        fact("2021-01-01", "2021-06-30", 180, "Q2-22", "2022-08-05", "10-Q"),
        # A late amendment must not replace the original report.
        fact("2022-01-01", "2022-06-30", 999, "Q2-22A", "2022-12-01", "10-Q/A"),
    ]
    income = [
        fact("2021-01-01", "2021-12-31", 40, "K-21", "2022-02-20", "10-K"),
        fact("2022-01-01", "2022-06-30", 30, "Q2-22", "2022-08-05", "10-Q"),
        fact("2021-01-01", "2021-06-30", 18, "Q2-22", "2022-08-05", "10-Q"),
    ]
    shares = [
        {"start": "2022-04-01", "end": "2022-06-30", "val": 50, "accn": "Q2-22", "filed": "2022-08-05", "form": "10-Q"},
        {"start": "2022-01-01", "end": "2022-06-30", "val": 51, "accn": "Q2-22", "filed": "2022-08-05", "form": "10-Q"},
    ]
    return {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": revenue}},
        "NetIncomeLoss": {"units": {"USD": income}},
        "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": shares}},
    }}}


def test_annual_report_gives_the_full_year_and_its_filing_date():
    year_end = quarterly.quarters(company(), REVENUE_TAGS)[0]
    assert (year_end.end, year_end.filed, year_end.form) == (date(2021, 12, 31), date(2022, 2, 20), "10-K")
    assert (year_end.revenue_ttm, year_end.net_income_ttm) == (400, 40)


def test_quarterly_report_gives_last_year_plus_this_year_to_date_minus_last_year_to_date():
    half_year = quarterly.quarters(company(), REVENUE_TAGS)[1]
    assert (half_year.end, half_year.filed) == (date(2022, 6, 30), date(2022, 8, 5))
    assert half_year.revenue_ttm == 400 + 260 - 180
    assert half_year.net_income_ttm == 40 + 30 - 18
    assert half_year.shares == 50  # the quarter's own share count, not the half year's


def test_amendments_do_not_add_or_replace_quarters():
    assert len(quarterly.quarters(company(), REVENUE_TAGS)) == 2


def test_missing_prior_year_comparison_gives_no_figure_rather_than_a_guess():
    facts = company()
    facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"] = [
        e for e in facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"] if e["end"] != "2021-06-30"
    ]
    assert quarterly.quarters(facts, REVENUE_TAGS)[1].revenue_ttm is None


def test_apple_trailing_revenue_at_december_2022_matches_its_filings():
    name = "data.sec.gov__api__xbrl__companyfacts__CIK0000320193.json"
    if not (sec.CACHE_DIR / name).exists():
        pytest.skip("SEC cache not present")
    rows = {q.end: q for q in quarterly.quarters(sec.company_facts(320193), ITEMS_BY_NAME["Revenue"].tags)}
    quarter = rows[date(2022, 12, 31)]
    # Fiscal 2022 $394,328M + December 2022 quarter $117,154M - December 2021 quarter $123,945M
    assert quarter.revenue_ttm == 387_537_000_000
    assert quarter.filed == date(2023, 2, 3)


def table():
    return pd.DataFrame({
        "ticker": ["A", "A"],
        "end": pd.to_datetime(["2022-03-31", "2022-06-30"]),
        "filed": pd.to_datetime(["2022-05-05", "2022-08-05"]),
        "revenue_growth": [0.10, 0.50],
    })


def test_period_end_version_sees_a_quarter_the_day_it_ends():
    view = timing.known(table(), pd.Timestamp("2022-06-30"), "period_end")
    assert view.loc["A", "revenue_growth"] == 0.50


def test_filing_date_version_sees_it_only_once_filed():
    assert timing.known(table(), pd.Timestamp("2022-06-30"), "filing_date").loc["A", "revenue_growth"] == 0.10
    assert timing.known(table(), pd.Timestamp("2022-08-04"), "filing_date").loc["A", "revenue_growth"] == 0.10
    assert timing.known(table(), pd.Timestamp("2022-08-05"), "filing_date").loc["A", "revenue_growth"] == 0.50


def test_stale_figures_are_dropped():
    assert timing.known(table(), pd.Timestamp("2023-06-30"), "filing_date").empty


def test_detectable_effect_shrinks_with_more_quarters():
    rng = np.random.default_rng(1)
    few, many = rng.normal(0, 0.02, 20), rng.normal(0, 0.02, 80)
    assert timing.detectable(many) < timing.detectable(few)
    assert timing.detectable(few) == pytest.approx(2.8 * few.std(ddof=1) / np.sqrt(20))
