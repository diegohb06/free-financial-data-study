"""Trailing-twelve-month figures for every fiscal quarter, with the date they became public.

Quarterly reports give year-to-date totals, and the fourth quarter is never
reported on its own. So the last twelve months at any quarter end are built as

    last full fiscal year + this year to date - last year to the same date

using only numbers from the quarterly report itself and the annual report
before it. The filing date of that quarterly report is the date the figure
became public.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from .parse import STATEMENT_FORMS, is_annual

# Original periodic reports. Amendments are ignored: the question here is when
# a period's results first became public.
ANNUAL = ("10-K", "10-KT")
PERIODIC = ANNUAL + ("10-Q", "10-QT")

NET_INCOME_TAGS = ("NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss")
SHARE_TAGS = ("WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic")


@dataclass(frozen=True)
class Quarter:
    end: date  # fiscal period end
    filed: date  # when the report was filed with the SEC
    form: str
    revenue_ttm: float | None
    net_income_ttm: float | None
    shares: float | None  # weighted diluted shares, on the share basis of the filing date


def _entries(facts: dict, tag: str, unit: str) -> list[dict]:
    return facts.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get(unit, [])


def _days(entry: dict) -> int:
    return (date.fromisoformat(entry["end"]) - date.fromisoformat(entry["start"])).days


def _annual_as_of(facts: dict, tag: str, near: date, when: str) -> float | None:
    """Full-year value for the fiscal year ending near a date, as known on a filing date."""
    known = [
        entry for entry in _entries(facts, tag, "USD")
        if "start" in entry and entry.get("form") in STATEMENT_FORMS and entry["filed"] <= when
        and abs((date.fromisoformat(entry["end"]) - near).days) <= 7
        and is_annual(date.fromisoformat(entry["start"]), date.fromisoformat(entry["end"]))
    ]
    return max(known, key=lambda e: e["filed"])["val"] if known else None


def _ttm(facts: dict, tags: tuple[str, ...], accn: str, end: date, form: str, filed: str) -> float | None:
    """Trailing twelve months to a period end, from one report; first tag that works wins."""
    for tag in tags:
        here = [
            e for e in _entries(facts, tag, "USD")
            if e["accn"] == accn and "start" in e
        ]
        current = [e for e in here if e["end"] == end.isoformat()]
        if not current:
            continue
        if form in ANNUAL:
            full_year = [e for e in current if is_annual(date.fromisoformat(e["start"]), end)]
            if full_year:
                return full_year[0]["val"]
            continue
        to_date = max(current, key=_days)
        if _days(to_date) > 300:
            continue
        year_ago = [
            e for e in here
            if abs((end - date.fromisoformat(e["end"])).days - 365) <= 10 and abs(_days(e) - _days(to_date)) <= 10
        ]
        last_year_end = date.fromisoformat(to_date["start"]) - timedelta(days=1)
        last_year = _annual_as_of(facts, tag, last_year_end, filed)
        if year_ago and last_year is not None:
            return last_year + to_date["val"] - year_ago[0]["val"]
    return None


def _shares(facts: dict, accn: str, end: date) -> float | None:
    for tag in SHARE_TAGS:
        here = [
            e for e in _entries(facts, tag, "shares")
            if e["accn"] == accn and e["end"] == end.isoformat() and "start" in e
        ]
        if here:
            return min(here, key=_days)["val"]  # the latest quarter is the most current count
    return None


def quarters(facts: dict, revenue_tags: tuple[str, ...]) -> list[Quarter]:
    """One row per fiscal quarter end, from the first periodic report that covered it."""
    reports: dict[str, tuple[date, str, str]] = {}  # accession -> (period end, form, filed)
    for tag in NET_INCOME_TAGS + revenue_tags:
        for entry in _entries(facts, tag, "USD"):
            if entry.get("form") not in PERIODIC or "start" not in entry:
                continue
            end = date.fromisoformat(entry["end"])
            known = reports.get(entry["accn"])
            if known is None or end > known[0]:
                reports[entry["accn"]] = (end, entry["form"], entry["filed"])

    first: dict[date, tuple[str, str, str]] = {}  # period end -> (filed, accession, form)
    for accn, (end, form, filed) in reports.items():
        if end not in first or (filed, accn) < first[end][:2]:
            first[end] = (filed, accn, form)

    rows = []
    for end, (filed, accn, form) in sorted(first.items()):
        rows.append(Quarter(
            end, date.fromisoformat(filed), form,
            _ttm(facts, revenue_tags, accn, end, form, filed),
            _ttm(facts, NET_INCOME_TAGS, accn, end, form, filed),
            _shares(facts, accn, end),
        ))
    return rows
