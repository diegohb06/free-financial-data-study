"""Shared helpers for the kill-test scripts."""

import csv
from datetime import date
from pathlib import Path

from groundtruth import filing, parse, sec
from groundtruth.items import Item, tags_for

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "reports" / "kill-test-full"

# "Fiscal 2019-2025": fiscal years ending in calendar 2019 through 2025.
FIRST_END = date(2019, 1, 1)
LAST_END = date(2025, 12, 31)


def companies() -> list[dict]:
    with open(HERE / "companies.csv") as handle:
        return list(csv.DictReader(handle))


def load_facts(company: dict) -> dict:
    facts = sec.company_facts(int(company["cik"]))
    if company["predecessor_cik"]:
        facts = parse.merge_predecessor(facts, sec.company_facts(int(company["predecessor_cik"])))
    return facts


def warm_annual_reports(company: dict, facts: dict) -> None:
    """Fetch the statements of every annual report since 2019 before they are needed one by one."""
    filings = {
        (int(company["cik"]), entry["accn"])
        for concept in facts["facts"]["us-gaap"].values()
        for entries in concept["units"].values()
        for entry in entries
        if entry.get("form") in parse.ANNUAL_FORMS and entry["filed"] >= FIRST_END.isoformat()
    }
    filing.warm(sorted(filings))


def statement_histories(company: dict, facts: dict, item: Item) -> dict[date, tuple[list[parse.Version], bool, int]]:
    """For each fiscal year: statement-confirmed versions, whether confirmed, and versions seen."""
    ciks = [int(c) for c in (company["cik"], company["predecessor_cik"]) if c]
    per_tag = [parse.versions(facts, item, (tag,)) for tag in tags_for(item, company["sector"])]
    result = {}
    for end in sorted({end for histories in per_tag for end in histories}):
        if end < FIRST_END:
            continue
        candidates = [histories[end] for histories in per_tag if end in histories]
        confirmed, found = filing.statement_history(ciks, candidates)
        seen = len(next(h for h in candidates if h[0].tag == confirmed[0].tag))
        result[end] = (confirmed, found, seen)
    return result
