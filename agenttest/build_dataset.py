"""Export the pipeline's data for the agent accuracy test (condition C).

One row per reported version of each value: what it is, what it counts, which
filing it came from (with a link), and when that filing became public. Only
versions confirmed on the face of a primary financial statement are included.

Writes agenttest/pipeline/values.csv, definitions.csv and README.md.
"""

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "killtest"))

from common import companies, load_facts, statement_histories, warm_annual_reports  # noqa: E402
from groundtruth import sec  # noqa: E402
from groundtruth.items import ITEMS, Item  # noqa: E402

OUT = HERE / "pipeline"

# One line item beyond the ten in the kill test, so the dataset can tell net
# income from income to common shareholders.
EXTRA_ITEMS = (
    Item(
        "NetIncomeToCommon", "income", "duration", "USD",
        ("NetIncomeLossAvailableToCommonStockholdersBasic",),
        "Net income available to common shareholders: net income attributable to the "
        "parent company minus preferred dividends and similar amounts.",
    ),
)
ALL_ITEMS = ITEMS + EXTRA_ITEMS

README = """# Ground Truth dataset (50 companies, annual, fiscal years ending 2019 onward)

`values.csv` has one row per reported version of a value. A value is one line
item for one company and one fiscal year. When a later filing reports a
different figure for the same year, that is a new version; nothing is overwritten.

Columns:

- `ticker`, `company`
- `item`: the standard line item (see `definitions.csv` for exactly what each one counts)
- `fiscal_year_end`: the last day of the fiscal year the value is for
- `version`: 1 is the value as first reported; higher numbers are later filings
- `is_first_reported`, `is_latest`: true/false flags for the first and the newest version
- `value`: in whole US dollars (or US dollars per share for EPSDiluted)
- `sec_tag`: the XBRL tag the company used for this value
- `filed`: the date the filing became public. A version was not known before this date
- `form`: the filing type (10-K, 10-Q, 8-K)
- `accession`, `source_url`: the exact SEC filing the value comes from

Every value has been confirmed on the face of a primary financial statement in
its filing. To answer "what was known on date D", take the version with the
latest `filed` date on or before D. Values that could not be confirmed on a
statement are left out, so a missing row means the dataset does not have it.
"""


def names() -> dict[str, str]:
    with open(HERE / "names.csv") as handle:
        return {row["ticker"]: row["name"] for row in csv.DictReader(handle)}


def filing_cik(company: dict, accession: str, own: set[str]) -> str:
    """The CIK a filing sits under: the predecessor's if the company did not file it itself."""
    return company["cik"] if accession in own or not company["predecessor_cik"] else company["predecessor_cik"]


def rows_for(company: dict, name: str) -> list[dict]:
    facts = load_facts(company)
    warm_annual_reports(company, facts)
    own = {
        entry["accn"]
        for concept in sec.company_facts(int(company["cik"]))["facts"]["us-gaap"].values()
        for entries in concept["units"].values() for entry in entries
    }
    rows = []
    for item in ALL_ITEMS:
        for end, (history, found, _) in statement_histories(company, facts, item).items():
            if not found:
                continue
            for number, version in enumerate(history, start=1):
                cik = filing_cik(company, version.accn, own)
                rows.append({
                    "ticker": company["ticker"], "company": name, "item": item.name,
                    "fiscal_year_end": end, "version": number,
                    "is_first_reported": number == 1, "is_latest": number == len(history),
                    "value": version.val, "sec_tag": version.tag, "filed": version.filed,
                    "form": version.form, "accession": version.accn,
                    "source_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                                  f"{version.accn.replace('-', '')}/{version.accn}-index.htm",
                })
    return rows


def main() -> None:
    OUT.mkdir(exist_ok=True)
    name = names()
    rows = []
    for company in companies():
        rows.extend(rows_for(company, name[company["ticker"]]))
        print(company["ticker"], flush=True)
    with open(OUT / "values.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with open(OUT / "definitions.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["item", "statement", "period", "definition", "sec_tags_in_priority_order"])
        for item in ALL_ITEMS:
            period = "full fiscal year" if item.kind == "duration" else "fiscal year end"
            writer.writerow([item.name, item.statement, period, item.definition, " | ".join(item.tags)])
    (OUT / "README.md").write_text(README)
    print(f"wrote {len(rows)} versions")


if __name__ == "__main__":
    main()
