"""Tests for classifying differences against the free source."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "killtest"))

import compare_free  # noqa: E402
from groundtruth.items import ITEMS_BY_NAME  # noqa: E402

REVENUE = ITEMS_BY_NAME["Revenue"]
NET_INCOME = ITEMS_BY_NAME["NetIncome"]


def test_equal_and_nearly_equal_values():
    assert compare_free.classify(REVENUE, 100.05, 100, 100)[0] == "match"
    assert compare_free.classify(REVENUE, 100.5, 100, 100)[0] == "small difference"
    assert compare_free.classify(REVENUE, 95, 100, 100) is None


def test_free_source_still_showing_the_original_figure():
    assert compare_free.classify(REVENUE, 100, 100, 80)[0] == "shows first-reported value"


def test_scale_and_sign_errors():
    assert compare_free.classify(REVENUE, 100_000, 100, 100) == ("true error", "scale: off by a factor of 1000")
    assert compare_free.classify(NET_INCOME, -50, 50, 50) == ("true error", "opposite sign")


def test_known_alternative_tag_is_an_expected_explanation():
    values = {"NetIncomeLoss": 100.0, "NetIncomeLossAvailableToCommonStockholdersBasic": 95.0}
    expected, discovered = compare_free.explanations(NET_INCOME, 95.0, 100.0, "NetIncomeLoss", values)
    assert expected == ["free source equals SEC tag NetIncomeLossAvailableToCommonStockholdersBasic; ours is NetIncomeLoss"]
    assert discovered == []


def test_bank_revenue_net_of_provisions_is_recognised():
    values = {"Revenues": 100.0, "ProvisionForCreditLosses": 6.0}
    expected, _ = compare_free.explanations(REVENUE, 94.0, 100.0, "Revenues", values)
    assert expected == ["free source equals total revenue minus provision for credit losses"]


def test_an_unlisted_tag_is_only_a_discovered_explanation():
    values = {"Revenues": 100.0, "OtherIncome": 7.0, "Unrelated": 40.0}
    expected, discovered = compare_free.explanations(REVENUE, 93.0, 100.0, "Revenues", values)
    assert expected == []
    assert discovered == ["free source equals our Revenues minus OtherIncome"]


def test_latest_values_reads_only_the_requested_year_and_kind():
    facts = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [
            {"start": "2021-01-01", "end": "2021-12-31", "val": 100, "filed": "2022-02-15", "form": "10-K"},
            {"start": "2021-01-01", "end": "2021-12-31", "val": 80, "filed": "2023-02-15", "form": "10-K"},
            {"start": "2021-10-01", "end": "2021-12-31", "val": 30, "filed": "2023-03-01", "form": "10-K"},
            {"start": "2021-01-01", "end": "2021-12-31", "val": 1, "filed": "2024-04-01", "form": "DEF 14A"},
        ]}},
        "Assets": {"units": {"USD": [{"end": "2021-12-31", "val": 500, "filed": "2022-02-15", "form": "10-K"}]}},
    }}}
    assert compare_free.latest_values(facts, date(2021, 12, 31), duration=True) == {"Revenues": 80}
    assert compare_free.latest_values(facts, date(2021, 12, 31), duration=False) == {"Assets": 500}
