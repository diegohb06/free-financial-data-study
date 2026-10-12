"""Checks against real SEC data in the local cache. Skipped if the cache is empty.

The expected figures are the ones printed in the companies' annual reports.
"""

from datetime import date

import pytest

from groundtruth import parse, sec
from groundtruth.items import ITEMS_BY_NAME

REVENUE = ITEMS_BY_NAME["Revenue"]


def cached_facts(cik: int) -> dict:
    name = f"data.sec.gov__api__xbrl__companyfacts__CIK{cik:010d}.json"
    if not (sec.CACHE_DIR / name).exists():
        pytest.skip("SEC cache not present; run killtest/restatements.py first")
    return sec.company_facts(cik)


def test_johnson_and_johnson_fiscal_2021_revenue_before_and_after_the_kenvue_recast():
    tag = "RevenueFromContractWithCustomerExcludingAssessedTax"
    history = parse.versions(cached_facts(200406), REVENUE, (tag,))[date(2022, 1, 2)]
    assert history[0].val == 93_775_000_000  # as first reported in February 2022
    assert history[0].filed == date(2022, 2, 17)
    assert history[-1].val == 78_740_000_000  # as recast after the spin-off


def test_apple_fiscal_2022_revenue_was_never_changed():
    history = parse.versions(cached_facts(320193), REVENUE)[date(2022, 9, 24)]
    assert {v.val for v in history} == {394_328_000_000}


def test_microsoft_fiscal_2023_revenue_and_point_in_time_lookup():
    history = parse.versions(cached_facts(789019), REVENUE)[date(2023, 6, 30)]
    assert history[0].val == 211_915_000_000
    assert parse.as_of(history, date(2023, 7, 1)) is None  # not yet filed
    assert parse.as_of(history, date(2023, 12, 31)).val == 211_915_000_000
