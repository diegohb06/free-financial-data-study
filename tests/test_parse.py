"""Tests for the parsing code, on small hand-built filings."""

from datetime import date

from groundtruth import parse
from groundtruth.items import ITEMS_BY_NAME, tags_for

REVENUE = ITEMS_BY_NAME["Revenue"]
ASSETS = ITEMS_BY_NAME["TotalAssets"]


def fact(end, val, accn, filed, start=None, form="10-K"):
    entry = {"end": end, "val": val, "accn": accn, "filed": filed, "form": form}
    if start:
        entry["start"] = start
    return entry


def company(**tags):
    return {"facts": {"us-gaap": {tag: {"units": {"USD": entries}} for tag, entries in tags.items()}}}


def restated_company():
    """FY2021 revenue first reported as 100, recast to 80 a year later."""
    return company(
        NetIncomeLoss=[
            fact("2021-12-31", 10, "A-21", "2022-02-15", start="2021-01-01"),
            fact("2022-12-31", 12, "A-22", "2023-02-15", start="2022-01-01"),
        ],
        Revenues=[
            fact("2021-12-31", 100, "A-21", "2022-02-15", start="2021-01-01"),
            fact("2021-12-31", 80, "A-22", "2023-02-15", start="2021-01-01"),
            fact("2022-12-31", 90, "A-22", "2023-02-15", start="2022-01-01"),
            # A quarter and a nine-month period must never be read as a year.
            fact("2021-12-31", 30, "A-21", "2022-02-15", start="2021-10-01"),
            fact("2021-09-30", 70, "Q-21", "2021-11-01", start="2021-01-01", form="10-Q"),
        ],
        Assets=[
            fact("2021-12-31", 500, "A-21", "2022-02-15"),
            fact("2021-12-31", 500, "Q-22", "2022-05-01", form="10-Q"),
            fact("2022-03-31", 510, "Q-22", "2022-05-01", form="10-Q"),
        ],
    )


def test_is_annual_accepts_52_and_53_week_years_only():
    assert parse.is_annual(date(2021, 1, 1), date(2021, 12, 31))
    assert parse.is_annual(date(2021, 1, 31), date(2022, 1, 29))  # 52 weeks
    assert parse.is_annual(date(2022, 1, 30), date(2023, 2, 4))  # 53 weeks
    assert not parse.is_annual(date(2021, 10, 1), date(2021, 12, 31))
    assert not parse.is_annual(date(2021, 1, 1), date(2021, 9, 30))


def test_first_and_latest_versions_are_kept_in_filing_order():
    history = parse.versions(restated_company(), REVENUE)[date(2021, 12, 31)]
    assert [v.val for v in history] == [100, 80]
    assert [v.accn for v in history] == ["A-21", "A-22"]
    assert parse.rel_diff(history[-1].val, history[0].val) == -0.2


def test_quarterly_and_year_to_date_values_are_ignored():
    histories = parse.versions(restated_company(), REVENUE)
    assert set(histories) == {date(2021, 12, 31), date(2022, 12, 31)}
    assert all(v.val != 30 and v.val != 70 for h in histories.values() for v in h)


def test_balance_sheet_values_only_at_fiscal_year_end():
    histories = parse.versions(restated_company(), ASSETS)
    assert set(histories) == {date(2021, 12, 31)}
    assert len(histories[date(2021, 12, 31)]) == 2  # 10-K, then the next 10-Q's comparative


def test_as_of_never_looks_ahead():
    history = parse.versions(restated_company(), REVENUE)[date(2021, 12, 31)]
    assert parse.as_of(history, date(2022, 2, 14)) is None
    assert parse.as_of(history, date(2022, 2, 15)).val == 100
    assert parse.as_of(history, date(2023, 2, 14)).val == 100
    assert parse.as_of(history, date(2023, 2, 15)).val == 80


def test_higher_priority_tag_wins_within_one_filing():
    facts = company(
        NetIncomeLoss=[fact("2021-12-31", 10, "A-21", "2022-02-15", start="2021-01-01")],
        Revenues=[fact("2021-12-31", 105, "A-21", "2022-02-15", start="2021-01-01")],
        RevenueFromContractWithCustomerExcludingAssessedTax=[
            fact("2021-12-31", 100, "A-21", "2022-02-15", start="2021-01-01")
        ],
    )
    (version,) = parse.versions(facts, REVENUE)[date(2021, 12, 31)]
    assert (version.tag, version.val) == ("Revenues", 105)


def test_one_tag_can_be_followed_on_its_own():
    facts = company(
        NetIncomeLoss=[fact("2021-12-31", 10, "A-21", "2022-02-15", start="2021-01-01")],
        RevenueFromContractWithCustomerExcludingAssessedTax=[
            fact("2021-12-31", 100, "A-21", "2022-02-15", start="2021-01-01"),
            fact("2021-12-31", 100, "A-22", "2023-02-15", start="2021-01-01"),
        ],
        # The later filing adds a broader total under a different tag.
        Revenues=[fact("2021-12-31", 105, "A-22", "2023-02-15", start="2021-01-01")],
    )
    tag = "RevenueFromContractWithCustomerExcludingAssessedTax"
    history = parse.versions(facts, REVENUE, (tag,))[date(2021, 12, 31)]
    assert [(v.tag, v.val) for v in history] == [(tag, 100), (tag, 100)]


def test_proxy_statement_figures_are_not_versions():
    facts = restated_company()
    facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"].append(
        fact("2021-12-31", 0.1, "P-23", "2023-04-01", start="2021-01-01", form="DEF 14A")
    )
    history = parse.versions(facts, REVENUE)[date(2021, 12, 31)]
    assert [v.val for v in history] == [100, 80]


def test_first_is_original_detects_a_missing_original_filing():
    history = parse.versions(restated_company(), REVENUE)
    assert parse.first_is_original(history[date(2021, 12, 31)])
    late = [parse.Version("Revenues", date(2020, 12, 31), 1, "A-22", "10-K", date(2023, 2, 15))]
    assert not parse.first_is_original(late)


def test_rel_diff_handles_negatives_and_zero():
    assert parse.rel_diff(5, 5) == 0
    assert parse.rel_diff(-50, -100) == 0.5  # a loss that shrank
    assert parse.rel_diff(0, 0) == 0
    assert parse.rel_diff(1, 0) == float("inf")


def test_predecessor_facts_are_used_only_before_the_successor_starts_filing():
    old = company(Revenues=[
        fact("2020-12-31", 100, "OLD-20", "2021-02-15", start="2020-01-01"),
        fact("2021-12-31", 55, "OLD-21", "2022-02-15", start="2021-01-01"),  # now a subsidiary
    ])
    new = company(Revenues=[
        fact("2020-12-31", 100, "NEW-21", "2022-02-10", start="2020-01-01"),
        fact("2021-12-31", 120, "NEW-21", "2022-02-10", start="2021-01-01"),
    ])
    merged = parse.merge_predecessor(new, old)["facts"]["us-gaap"]["Revenues"]["units"]["USD"]
    assert sorted(e["accn"] for e in merged) == ["NEW-21", "NEW-21", "OLD-20"]


def test_banks_never_use_contract_revenue_as_total_revenue():
    assert "RevenueFromContractWithCustomerExcludingAssessedTax" not in tags_for(REVENUE, "Banks")
    assert "RevenueFromContractWithCustomerExcludingAssessedTax" in tags_for(REVENUE, "Technology")
