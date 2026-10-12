"""Kill test, part 1: how often does the first-reported value differ from the latest?

Every value is first confirmed on the face of a primary financial statement in
its original filing, and every changed value on the face of the later filing.

Writes one row per company, item and fiscal year to
reports/kill-test-full/restatements.csv, and tagged proxy-statement figures
that contradict the financial statements to filer_errors.csv.
"""

import csv
from datetime import date

from groundtruth import parse
from groundtruth.items import ITEMS, ITEMS_BY_NAME

from common import LAST_END, RESULTS, companies, load_facts, statement_histories, warm_annual_reports

FIELDS = [
    "ticker", "size", "sector", "item", "fiscal_year_end", "n_versions", "first_is_original",
    "on_statement", "tag", "first_value", "first_form", "first_filed", "first_accession",
    "latest_value", "latest_form", "latest_filed", "latest_accession", "rel_diff",
]


def rows_for(company: dict, facts: dict) -> list[dict]:
    rows = []
    for item in ITEMS:
        for end, (history, found, seen) in statement_histories(company, facts, item).items():
            if end > LAST_END:
                continue
            first, latest = history[0], history[-1]
            rows.append({
                "ticker": company["ticker"], "size": company["size"], "sector": company["sector"],
                "item": item.name, "fiscal_year_end": end, "n_versions": seen,
                "first_is_original": parse.first_is_original(history),
                "on_statement": found, "tag": first.tag,
                "first_value": first.val, "first_form": first.form,
                "first_filed": first.filed, "first_accession": first.accn,
                "latest_value": latest.val, "latest_form": latest.form,
                "latest_filed": latest.filed, "latest_accession": latest.accn,
                "rel_diff": parse.rel_diff(latest.val, first.val),
            })
    return rows


def proxy_errors(company: dict, facts: dict) -> list[dict]:
    """Net income tagged in a proxy statement at a different scale or sign than the 10-K."""
    statement = {
        end: history[-1]
        for end, history in parse.versions(facts, ITEMS_BY_NAME["NetIncome"], ("NetIncomeLoss",)).items()
    }
    rows = []
    for entry in facts["facts"]["us-gaap"].get("NetIncomeLoss", {}).get("units", {}).get("USD", []):
        end = date.fromisoformat(entry["end"])
        if not entry.get("form", "").startswith("DEF") or end not in statement or "start" not in entry:
            continue
        if not parse.is_annual(date.fromisoformat(entry["start"]), end):
            continue
        filed_value, proxy_value = statement[end].val, entry["val"]
        if filed_value == 0 or proxy_value == 0:
            continue
        ratio = proxy_value / filed_value
        if ratio < 0 or not 0.5 <= ratio <= 2:
            rows.append({
                "ticker": company["ticker"], "fiscal_year_end": end, "tag": "NetIncomeLoss",
                "statement_value": filed_value, "statement_accession": statement[end].accn,
                "proxy_value": proxy_value, "proxy_form": entry["form"],
                "proxy_filed": entry["filed"], "proxy_accession": entry["accn"],
                "ratio": ratio,
            })
    return rows


def write(name: str, rows: list[dict], fields: list[str]) -> None:
    with open(RESULTS / name, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)



def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    rows, errors = [], []
    for company in companies():
        facts = load_facts(company)
        warm_annual_reports(company, facts)
        rows.extend(rows_for(company, facts))
        errors.extend(proxy_errors(company, facts))
        print(company["ticker"], flush=True)
    write("restatements.csv", rows, FIELDS)
    if errors:
        write("filer_errors.csv", errors, list(errors[0]))
    print(f"wrote {len(rows)} values, {len(errors)} proxy-statement errors")


if __name__ == "__main__":
    main()
