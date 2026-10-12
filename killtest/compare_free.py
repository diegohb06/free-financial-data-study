"""Kill test, part 2: compare our SEC values with a free source (Yahoo Finance via yfinance).

Writes one row per compared value to reports/kill-test-full/comparison.csv.
Only our own values and the classified result are stored, never the free
source's figures.
"""

import csv
import pickle
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

from groundtruth import parse
from groundtruth.items import ITEMS, Item

from common import RESULTS, companies, load_facts

# Free-source row label for each of our items, and the statement it is on.
LABELS = {
    "Revenue": ("income_stmt", "Total Revenue"),
    "OperatingIncome": ("income_stmt", "Operating Income"),
    "NetIncome": ("income_stmt", "Net Income"),
    "EPSDiluted": ("income_stmt", "Diluted EPS"),
    "TotalAssets": ("balance_sheet", "Total Assets"),
    "TotalLiabilities": ("balance_sheet", "Total Liabilities Net Minority Interest"),
    "StockholdersEquity": ("balance_sheet", "Stockholders Equity"),
    "Cash": ("balance_sheet", "Cash And Cash Equivalents"),
    "OperatingCashFlow": ("cashflow", "Operating Cash Flow"),
    "CapEx": ("cashflow", "Capital Expenditure"),
}

MATCH = 0.001  # within 0.1%: the same number
MISMATCH = 0.01  # more than 1%: a different number, to be classified

# Sums and differences of SEC tags that free sources are known to show under a
# plain label. Each is (description, [(sign, tag), ...]).
FORMULAS = {
    "Revenue": [
        ("total revenue minus provision for credit losses",
         [(1, "Revenues"), (-1, "ProvisionForCreditLosses")]),
        ("total revenue minus provision for loan and lease losses",
         [(1, "Revenues"), (-1, "ProvisionForLoanLeaseAndOtherLosses")]),
        ("total revenue minus provision for loan losses",
         [(1, "Revenues"), (-1, "ProvisionForLoanAndLeaseLosses")]),
        ("net interest income plus noninterest income",
         [(1, "InterestIncomeExpenseNet"), (1, "NoninterestIncome")]),
        ("interest income plus noninterest income",
         [(1, "InterestAndDividendIncomeOperating"), (1, "NoninterestIncome")]),
        ("total revenue minus interest expense",
         [(1, "Revenues"), (-1, "InterestExpense")]),
    ],
    "TotalLiabilities": [
        ("liabilities and equity minus total equity including noncontrolling interests",
         [(1, "LiabilitiesAndStockholdersEquity"),
          (-1, "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")]),
        ("liabilities and equity minus shareholders' equity",
         [(1, "LiabilitiesAndStockholdersEquity"), (-1, "StockholdersEquity")]),
    ],
    "NetIncome": [
        ("net income minus preferred dividends",
         [(1, "NetIncomeLoss"), (-1, "PreferredStockDividendsIncomeStatementImpact")]),
    ],
    "Cash": [
        ("cash plus short-term investments",
         [(1, "CashAndCashEquivalentsAtCarryingValue"), (1, "ShortTermInvestments")]),
        ("cash and due from banks plus interest-bearing deposits",
         [(1, "CashAndDueFromBanks"), (1, "InterestBearingDepositsInBanks")]),
    ],
    "CapEx": [
        ("property purchases plus software or intangible purchases",
         [(1, "PaymentsToAcquirePropertyPlantAndEquipment"), (1, "PaymentsToAcquireIntangibleAssets")]),
    ],
}


def close(a: float, b: float, tolerance: float = MATCH) -> bool:
    return abs(parse.rel_diff(a, b)) <= tolerance if b else a == b


def latest_values(facts: dict, end: date, duration: bool) -> dict[str, float]:
    """Latest reported value of every tag for one fiscal year (or year end)."""
    values = {}
    for tag, concept in facts["facts"]["us-gaap"].items():
        best = None
        for unit in ("USD", "USD/shares"):
            for entry in concept.get("units", {}).get(unit, []):
                if entry["end"] != end.isoformat() or entry.get("form") not in parse.STATEMENT_FORMS:
                    continue
                if duration != ("start" in entry):
                    continue
                if duration and not parse.is_annual(date.fromisoformat(entry["start"]), end):
                    continue
                if best is None or entry["filed"] >= best["filed"]:
                    best = entry
        if best:
            values[tag] = best["val"]
    return values


def explanations(item: Item, theirs: float, latest: float, tag: str, values: dict[str, float]) -> tuple[list[str], list[str]]:
    """Ways the free source's number can be rebuilt from SEC tags: (expected, discovered).

    Expected explanations come from the item's listed alternative tags and the
    known formulas. Discovered ones are any other single tag, or our value plus
    or minus a single tag; they are only believed if they repeat across years.
    """
    expected, discovered = [], []
    listed = set(item.tags + item.alternatives)
    for other, value in values.items():
        if other != tag and close(theirs, value):
            (expected if other in listed else discovered).append(f"free source equals SEC tag {other}; ours is {tag}")
    for description, terms in FORMULAS.get(item.name, []):
        if all(term_tag in values for _, term_tag in terms):
            if close(theirs, sum(sign * values[term_tag] for sign, term_tag in terms)):
                expected.append(f"free source equals {description}")
    gap = theirs - latest
    for other, value in values.items():
        if other != tag and value and abs(abs(value) - abs(gap)) <= 0.005 * abs(gap):
            sign = "plus" if (gap > 0) == (value > 0) else "minus"
            discovered.append(f"free source equals our {tag} {sign} {other}")
    return expected, discovered


def classify(item: Item, theirs: float, first: float, latest: float) -> tuple[str, str] | None:
    """Result for a value that needs no tag search; None if it is a mismatch to explain."""
    if close(theirs, latest):
        return "match", ""
    if abs(parse.rel_diff(theirs, latest)) <= MISMATCH:
        return "small difference", "within 1%"
    if not close(first, latest, MISMATCH) and close(theirs, first):
        return "shows first-reported value", "free source has the original figure, not the restated one"
    if latest and close(theirs, -latest):
        return "true error", "opposite sign"
    for factor in (1e3, 1e6, 1e-3, 1e-6):
        if latest and close(theirs, latest * factor, MISMATCH):
            return "true error", f"scale: off by a factor of {factor:g}"
    return None


def fetch(ticker: str, scratch: Path | None) -> dict[str, pd.DataFrame]:
    """The free source's annual statements. Held in memory; kept on disk only in a scratch folder."""
    path = scratch / f"{ticker}.pkl" if scratch else None
    if path and path.exists():
        return pickle.loads(path.read_bytes())
    source = yf.Ticker(ticker)
    statements = {name: getattr(source, name) for name in ("income_stmt", "balance_sheet", "cashflow")}
    if path:
        path.write_bytes(pickle.dumps(statements))
    return statements


AS_REPORTED = {"OperatingIncome": "Total Operating Income As Reported"}


def main() -> None:
    scratch = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    ours = pd.read_csv(RESULTS / "restatements.csv", parse_dates=["fiscal_year_end"])
    ours = ours[ours.first_is_original & ours.on_statement]
    items = {item.name: item for item in ITEMS}
    rows = []
    for company in companies():
        ticker = company["ticker"]
        facts = load_facts(company)
        statements = fetch(ticker, scratch)
        pending = []
        for _, row in ours[ours.ticker == ticker].iterrows():
            statement, label = LABELS[row["item"]]
            table = statements[statement]
            if table is None or label not in table.index:
                continue
            near = [c for c in table.columns if abs((c - row.fiscal_year_end).days) <= 7]
            if not near or pd.isna(table.loc[label, near[0]]):
                continue
            item, end = items[row["item"]], row.fiscal_year_end.date()
            theirs = float(table.loc[label, near[0]])
            if item.name == "CapEx":
                theirs = abs(theirs)  # shown as a negative cash flow; a convention, not a difference
            record = {
                "ticker": ticker, "size": company["size"], "sector": company["sector"],
                "item": item.name, "fiscal_year_end": end, "our_tag": row.tag,
                "our_first_value": row.first_value, "our_latest_value": row.latest_value,
                "restated_over_1pct": not close(row.first_value, row.latest_value, MISMATCH),
                "free_source_vs_our_latest": round(parse.rel_diff(theirs, row.latest_value), 4),
            }
            rows.append(record)
            verdict = classify(item, theirs, row.first_value, row.latest_value)
            if verdict:
                record["result"], record["explanation"] = verdict
                continue
            expected, discovered = explanations(
                item, theirs, row.latest_value, row.tag, latest_values(facts, end, item.kind == "duration")
            )
            other_label = AS_REPORTED.get(item.name)
            if other_label in table.index and close(float(table.loc[other_label, near[0]]), row.latest_value):
                expected.append(
                    "free source's headline figure is its own standardized calculation; "
                    "its separate 'as reported' line equals ours"
                )
            if expected:
                record["result"], record["explanation"] = "definition difference", expected[0]
            else:
                pending.append((record, discovered))
        # A discovered explanation is believed only if it holds in at least two years.
        for record, discovered in pending:
            repeated = [
                e for e in discovered
                if sum(e in d and r["item"] == record["item"] for r, d in pending) >= 2
            ]
            if repeated:
                record["result"], record["explanation"] = "definition difference", repeated[0]
            else:
                record["result"], record["explanation"] = "unexplained", ""
        print(ticker, flush=True)
    with open(RESULTS / "comparison.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} comparisons")


if __name__ == "__main__":
    main()
