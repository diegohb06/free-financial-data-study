"""Turn SEC companyfacts JSON into every reported version of each annual value.

A "version" is one filing's statement of one line item for one fiscal year.
Nothing is overwritten: the first version is what was first reported, later
versions are what later filings said about the same year.
"""

from dataclasses import dataclass
from datetime import date

from .items import Item

ANNUAL_FORMS = ("10-K", "10-K/A", "10-KT", "10-KT/A")
# Forms that carry financial statements. Proxy statements (DEF 14A) also tag
# net income, but rounded and outside the audited statements, so they are not
# versions of a reported value.
STATEMENT_FORMS = ANNUAL_FORMS + ("10-Q", "10-Q/A", "10-QT", "10-QT/A", "8-K", "8-K/A")
# Tags used only to learn which dates are fiscal year ends.
YEAR_END_TAGS = (
    "NetIncomeLoss",
    "ProfitLoss",
    "NetCashProvidedByUsedInOperatingActivities",
)
# A first version filed later than this after the period end is not the
# original report (the original was filed without usable XBRL, or under a tag
# we do not map), so "first reported" is unknown for that value.
ORIGINAL_FILING_MAX_DAYS = 200


@dataclass(frozen=True)
class Version:
    tag: str
    end: date
    val: float
    accn: str
    form: str
    filed: date


def is_annual(start: date, end: date) -> bool:
    """True for a 52/53-week or 12-month period."""
    return 350 <= (end - start).days <= 380


def _entries(facts: dict, tag: str, unit: str) -> list[dict]:
    return facts.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get(unit, [])


def merge_predecessor(successor: dict, predecessor: dict) -> dict:
    """Combine a company's facts with those of the CIK it used to file under.

    Predecessor facts are kept only from filings made before the successor's
    first filing; after that the predecessor may live on as a subsidiary with
    different numbers.
    """
    successor_tags = successor.get("facts", {}).get("us-gaap", {})
    filed_dates = [
        entry["filed"]
        for concept in successor_tags.values()
        for entries in concept.get("units", {}).values()
        for entry in entries
    ]
    cutoff = min(filed_dates) if filed_dates else "9999-12-31"

    merged: dict = {}
    for source, keep in ((predecessor, lambda e: e["filed"] < cutoff), (successor, lambda e: True)):
        for tag, concept in source.get("facts", {}).get("us-gaap", {}).items():
            for unit, entries in concept.get("units", {}).items():
                kept = [e for e in entries if keep(e)]
                if kept:
                    merged.setdefault(tag, {"units": {}})["units"].setdefault(unit, []).extend(kept)
    return {"facts": {"us-gaap": merged}}


def fiscal_year_ends(facts: dict) -> set[date]:
    """Dates on which a fiscal year ended, taken from annual reports."""
    ends = set()
    for tag in YEAR_END_TAGS:
        for entry in _entries(facts, tag, "USD"):
            if entry.get("form") in ANNUAL_FORMS and "start" in entry:
                start, end = date.fromisoformat(entry["start"]), date.fromisoformat(entry["end"])
                if is_annual(start, end):
                    ends.add(end)
    return ends


def versions(facts: dict, item: Item, tags: tuple[str, ...] | None = None) -> dict[date, list[Version]]:
    """Every version of an item, by fiscal year end, oldest filing first.

    When one filing reports several candidate tags for the same year, the
    highest-priority tag wins, so each filing contributes at most one version.
    """
    tags = item.tags if tags is None else tags
    year_ends = fiscal_year_ends(facts)
    chosen: dict[tuple[date, str], tuple[int, Version]] = {}
    for priority, tag in enumerate(tags):
        for entry in _entries(facts, tag, item.unit):
            end = date.fromisoformat(entry["end"])
            if end not in year_ends or entry.get("form") not in STATEMENT_FORMS:
                continue
            if item.kind == "duration":
                if "start" not in entry or not is_annual(date.fromisoformat(entry["start"]), end):
                    continue
            elif "start" in entry:
                continue
            version = Version(
                tag, end, entry["val"], entry["accn"], entry.get("form", ""),
                date.fromisoformat(entry["filed"]),
            )
            key = (end, version.accn)
            if key not in chosen or priority < chosen[key][0]:
                chosen[key] = (priority, version)

    by_end: dict[date, list[Version]] = {}
    for (end, _), (_, version) in chosen.items():
        by_end.setdefault(end, []).append(version)
    for end in by_end:
        by_end[end].sort(key=lambda v: (v.filed, v.accn))
    return by_end


def as_of(history: list[Version], when: date) -> Version | None:
    """The latest version that was public on a date: no look-ahead."""
    known = [v for v in history if v.filed <= when]
    return known[-1] if known else None


def first_is_original(history: list[Version]) -> bool:
    """Whether the earliest version we hold is the original report of the year."""
    first = history[0]
    return (first.filed - first.end).days <= ORIGINAL_FILING_MAX_DAYS


def rel_diff(new: float, old: float) -> float:
    """Relative change from old to new; 0 when both are zero."""
    if new == old:
        return 0.0
    if old == 0:
        return float("inf")
    return (new - old) / abs(old)
