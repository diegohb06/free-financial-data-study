"""Build the 60 questions and their answer key from the pipeline dataset.

Run once, before any agent answers anything. The questions and key are then
committed, so they cannot be adjusted to fit the results. Selection is by the
fixed rules below and a fixed random seed.

Writes agenttest/questions.json (what the agents see) and
agenttest/answer_key.json (answers, and known wrong values for classifying mistakes).
"""

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "killtest"))

from common import companies, load_facts  # noqa: E402
from groundtruth import parse  # noqa: E402

SEED = 2026
LAST_YEAR_END = "2025-12-31"
SPECIAL_SECTORS = ("Banks", "Energy")  # revenue means something different there

PHRASES = {
    "Revenue": "total revenue (the total revenue line on its income statement)",
    "NetIncome": "net income attributable to the company",
    "TotalAssets": "total assets",
    "OperatingIncome": "operating income as shown on the company's own income statement "
                       "(not a standardized or adjusted figure)",
    "NetIncomeToCommon": "net income available (applicable) to common shareholders, after preferred dividends",
    "CapEx": "cash paid for purchases of property, plant and equipment (capital expenditures) "
             "as shown on its cash flow statement",
    "OperatingCashFlow": "net cash provided by operating activities",
    "Cash": "cash and cash equivalents",
    "StockholdersEquity": "total shareholders' equity attributable to the company",
    "TotalLiabilities": "total liabilities",
}
DEFINITION_PHRASES = {
    ("JPM", "Revenue"): "total net revenue as shown on its consolidated income statement",
    ("BAC", "Revenue"): "total revenue, net of interest expense, as shown on its consolidated income statement",
    ("XOM", "Revenue"): "total revenues and other income as shown on its consolidated income statement",
    ("CVX", "Revenue"): "total revenues and other income as shown on its consolidated income statement",
    ("ZION", "NetIncome"): "net income before deducting preferred stock dividends",
    ("WAL", "NetIncome"): "net income before deducting preferred stock dividends",
}
# Definition-sensitive questions: (ticker, item, how many fiscal years to ask about).
DEFINITION_CASES = [
    ("JPM", "Revenue", 2), ("BAC", "Revenue", 1), ("XOM", "Revenue", 2), ("CVX", "Revenue", 2),
    ("KO", "OperatingIncome", 1), ("HSIC", "OperatingIncome", 1),
    ("JBL", "OperatingIncome", 1), ("UGI", "OperatingIncome", 1),
    ("JPM", "NetIncomeToCommon", 1), ("BAC", "NetIncomeToCommon", 1),
    ("ZION", "NetIncome", 1), ("WAL", "NetIncome", 1),
]
DURATION_ITEMS = ("Revenue", "OperatingIncome", "NetIncome", "CapEx", "OperatingCashFlow")

rng = random.Random(SEED)
values = pd.read_csv(HERE / "pipeline" / "values.csv")
values = values[values.fiscal_year_end <= LAST_YEAR_END]
company = {c["ticker"]: c for c in companies()}
histories = {
    key: rows.sort_values("version")
    for key, rows in values.groupby(["ticker", "item", "fiscal_year_end"])
}
_facts = {}


def facts_for(ticker: str) -> dict:
    if ticker not in _facts:
        _facts[ticker] = load_facts(company[ticker])
    return _facts[ticker]


def long_date(iso: str) -> str:
    day = date.fromisoformat(iso)
    return f"{day:%B} {day.day}, {day.year}"


def unrestated(key) -> bool:
    return histories[key].value.nunique() == 1


def change(key) -> float:
    rows = histories[key]
    return abs(parse.rel_diff(rows.value.iloc[-1], rows.value.iloc[0]))


# When each company's annual report for each fiscal year was filed.
annual_reports: dict[str, dict[str, str]] = {}
for (ticker, item, end), rows in histories.items():
    if item == "TotalAssets" and rows.form.iloc[0].startswith("10-K"):
        annual_reports.setdefault(ticker, {})[end] = rows.filed.iloc[0]


def complete(key, cutoff: str = "2026-10-11") -> bool:
    """Whether the dataset holds the value from every annual report that should repeat it.

    An income or cash flow statement shows three years, so the reports for the
    next two fiscal years repeat a year's figure. If the dataset is missing one
    of those (the company switched tags, or the figure was not on the statement),
    it cannot be sure what the company last said, so the value is not used.
    """
    ticker, _, end = key
    seen = set(histories[key].filed)
    for years in (1, 2):
        target = date.fromisoformat(end) + timedelta(days=365 * years)
        for report_end, filed in annual_reports.get(ticker, {}).items():
            if abs((date.fromisoformat(report_end) - target).days) <= 10 and filed <= cutoff and filed not in seen:
                return False
    return True


def wrong_values(ticker: str, tag: str, end: str, answer: float, annual: bool) -> dict[str, list[float]]:
    """Other real numbers an answer might be confused with, by kind of mistake."""
    other_versions, other_periods, other_definitions = set(), set(), set()
    for name, concept in facts_for(ticker)["facts"]["us-gaap"].items():
        for entry in concept.get("units", {}).get("USD", []):
            is_duration = "start" in entry
            same_period = entry["end"] == end and is_duration == annual and (
                not annual or parse.is_annual(date.fromisoformat(entry["start"]), date.fromisoformat(end))
            )
            if name == tag and same_period:
                other_versions.add(entry["val"])
            elif name == tag:
                other_periods.add(entry["val"])
            elif same_period:
                other_definitions.add(entry["val"])
    return {
        "restated_vs_original": sorted(other_versions - {answer}),
        "wrong_period": sorted(other_periods - other_versions - {answer}),
        "wrong_definition": sorted(other_definitions - other_versions - {answer}),
    }


def value_question(category: str, key, basis: str, row, phrase: str | None = None, lead: str = "") -> dict:
    ticker, item, end = key
    name = histories[key].company.iloc[0]
    phrase = phrase or DEFINITION_PHRASES.get((ticker, item)) or PHRASES[item]
    when = f"as of {long_date(end)} (its fiscal year end)" if item in ("TotalAssets", "Cash", "StockholdersEquity", "TotalLiabilities") \
        else f"for the fiscal year ended {long_date(end)}"
    return {
        "category": category, "ticker": ticker, "item": item, "fiscal_year_end": end, "basis": basis,
        "question": f"{lead}What was {name}'s ({ticker}) {phrase} {when}?",
        "unit": "USD", "answer": float(row.value), "tolerance": {"relative": 0.005},
        "source": {"sec_tag": row.sec_tag, "filed": row.filed, "accession": row.accession, "url": row.source_url},
        "known_wrong_values": wrong_values(ticker, row.sec_tag, end, float(row.value), item in DURATION_ITEMS + ("NetIncomeToCommon",)),
    }


def pick(pool: list, count: int, used: set, one_per_company: bool = True) -> list:
    pool = sorted(pool)
    rng.shuffle(pool)
    chosen = []
    for key in pool:
        if len(chosen) == count:
            break
        if one_per_company and key[0] in used:
            continue
        chosen.append(key)
        used.add(key[0])
    assert len(chosen) == count, (len(chosen), count)
    return chosen


def lookups() -> list[dict]:
    """15 plain lookups: values never restated, outside banks and energy, spread across sizes."""
    sizes = {"Revenue": "LLMMS", "NetIncome": "LMMSS", "TotalAssets": "LLMSS"}
    used, questions = set(), []
    for item, mix in sizes.items():
        for letter, size in (("L", "large"), ("M", "mid"), ("S", "small")):
            pool = [
                key for key in histories
                if key[1] == item and unrestated(key) and complete(key) and company[key[0]]["size"] == size
                and company[key[0]]["sector"] not in SPECIAL_SECTORS
                and (item != "NetIncome" or histories[key].sec_tag.iloc[0] == "NetIncomeLoss")
            ]
            for key in pick(pool, mix.count(letter), used):
                questions.append(value_question("lookup", key, "never restated", histories[key].iloc[0]))
    return questions


def definitions() -> list[dict]:
    """15 questions where the label alone is ambiguous: most recent unrestated fiscal years."""
    questions = []
    for ticker, item, count in DEFINITION_CASES:
        keys = sorted(
            (key for key in histories
             if key[:2] == (ticker, item) and unrestated(key) and complete(key) and key[2] <= "2024-12-31"),
            key=lambda k: k[2], reverse=True,
        )[:count]
        assert len(keys) == count, (ticker, item)
        for key in keys:
            questions.append(value_question("definition", key, "never restated", histories[key].iloc[0]))
    return questions


def restated_pool() -> list:
    return [
        key for key in histories
        if key[1] in DURATION_ITEMS and change(key) > 0.01 and complete(key)
    ]


def restatements(used_values: set) -> list[dict]:
    """10 restated values, one per company: 5 asked as first reported, 5 as latest."""
    used, questions = set(), []
    revenue_first = sorted(restated_pool(), key=lambda k: k[1] != "Revenue")
    by_company = {}
    for key in revenue_first:
        by_company.setdefault(key[0], []).append(key)
    tickers = sorted(by_company)
    rng.shuffle(tickers)
    for index, ticker in enumerate(tickers[:10]):
        options = [k for k in by_company[ticker] if k[1] == by_company[ticker][0][1]]
        key = rng.choice(sorted(options))
        used_values.add(key)
        rows = histories[key]
        if index % 2 == 0:
            questions.append(value_question(
                "restatement", key, "first reported", rows.iloc[0],
                lead="As first reported in the company's original annual report for that year (before any later restatement or recast): ",
            ))
        else:
            questions.append(value_question(
                "restatement", key, "latest", rows.iloc[-1],
                lead="As most recently reported by the company in its SEC filings (the latest restated or recast figure, as of October 2026): ",
            ))
    assert len(questions) == 10
    return questions


def point_in_time(used_values: set) -> list[dict]:
    """10 restated values asked as of a date: 5 before the first change, 5 after a change."""
    pool = sorted(k for k in restated_pool() if k not in used_values)
    rng.shuffle(pool)
    questions, per_company, wanted = [], {}, ["before"] * 5 + ["after"] * 5
    for key in pool:
        if not wanted:
            break
        if per_company.get(key[0], 0) >= 2:
            continue
        rows = histories[key].reset_index(drop=True)
        changes = [i for i in range(1, len(rows)) if rows.value[i] != rows.value[i - 1]]
        index = changes[0] - 1 if wanted[0] == "before" else rng.choice(changes)
        start = date.fromisoformat(rows.filed[index])
        stop = date.fromisoformat(rows.filed[index + 1]) if index + 1 < len(rows) else date(2026, 9, 30)
        if (stop - start).days < 60:
            continue
        when = start + (stop - start) / 2
        when = date(when.year, when.month, 15)
        if not start + timedelta(days=20) <= when <= stop - timedelta(days=20):
            continue
        wanted.pop(0)
        per_company[key[0]] = per_company.get(key[0], 0) + 1
        questions.append(value_question(
            "point_in_time", key, f"as known on {when.isoformat()}", rows.iloc[index],
            lead=f"Going only by SEC filings that were public on {long_date(when.isoformat())} "
                 f"(use the most recent filing on or before that date that reports the figure): ",
        ))
    assert len(questions) == 10
    return questions


def derived(used: set) -> list[dict]:
    """10 ratios from values never restated: 4 revenue growth, 3 net margin, 3 operating margin."""
    def first(ticker, item, end):
        key = (ticker, item, end)
        usable = key in histories and unrestated(key) and complete(key)
        return float(histories[key].value.iloc[0]) if usable else None

    def prior_end(ticker, item, end):
        target = date.fromisoformat(end) - timedelta(days=365)
        near = [k[2] for k in histories if k[:2] == (ticker, item) and abs((date.fromisoformat(k[2]) - target).days) <= 10]
        return near[0] if near else None

    def next_end(ticker, item, end):
        target = date.fromisoformat(end) + timedelta(days=365)
        near = [k[2] for k in histories if k[:2] == (ticker, item) and abs((date.fromisoformat(k[2]) - target).days) <= 10]
        return near[0] if near else None

    def growth(ticker, end):
        before = prior_end(ticker, "Revenue", end)
        now, then = first(ticker, "Revenue", end), before and first(ticker, "Revenue", before)
        return (now / then - 1) * 100 if now and then else None

    def margin(numerator):
        def ratio(ticker, end):
            top, bottom = first(ticker, numerator, end), first(ticker, "Revenue", end)
            return top / bottom * 100 if top is not None and bottom else None
        return ratio

    kinds = [
        ("revenue growth", growth, 4,
         "By what percentage did {name}'s ({ticker}) total revenue change in the fiscal year ended {end}, "
         "compared with the previous fiscal year?"),
        ("net margin", margin("NetIncome"), 3,
         "What was {name}'s ({ticker}) net profit margin (net income attributable to the company divided by "
         "total revenue) for the fiscal year ended {end}?"),
        ("operating margin", margin("OperatingIncome"), 3,
         "What was {name}'s ({ticker}) operating margin (operating income as shown on its own income "
         "statement divided by total revenue) for the fiscal year ended {end}?"),
    ]
    questions = []
    for label, formula, count, template in kinds:
        pool = [
            (ticker, "Revenue", end) for (ticker, item, end) in histories
            if item == "Revenue" and company[ticker]["sector"] not in SPECIAL_SECTORS
            and formula(ticker, end) is not None and abs(formula(ticker, end)) >= 3
        ]
        for ticker, _, end in pick(pool, count, used):
            neighbours = [e for e in (prior_end(ticker, "Revenue", end), next_end(ticker, "Revenue", end)) if e]
            questions.append({
                "category": "derived", "ticker": ticker, "item": label, "fiscal_year_end": end,
                "basis": "never restated",
                "question": template.format(name=histories[(ticker, "Revenue", end)].company.iloc[0],
                                            ticker=ticker, end=long_date(end)),
                "unit": "percent", "answer": round(formula(ticker, end), 4),
                "tolerance": {"relative": 0.005, "absolute_points": 0.05},
                "source": {"formula": label, "inputs": "first-reported values from the pipeline dataset"},
                "known_wrong_values": {
                    "restated_vs_original": [],
                    "wrong_period": sorted(round(formula(ticker, e), 4) for e in neighbours if formula(ticker, e) is not None),
                    "wrong_definition": [],
                },
            })
    return questions


def main() -> None:
    used_values: set = set()
    key = lookups() + definitions() + restatements(used_values) + point_in_time(used_values)
    key += derived({q["ticker"] for q in key if q["category"] == "lookup"})
    assert len(key) == 60
    # Shuffle so the id says nothing about the category, then deal into six batches of ten.
    rng.shuffle(key)
    order = ["lookup", "definition", "restatement", "point_in_time", "derived"]
    key.sort(key=lambda q: order.index(q["category"]))  # group, keeping shuffled order within a category
    dealt = sorted(range(60), key=lambda i: (i % 6, i))
    key = [key[i] for i in dealt]
    for number, question in enumerate(key, start=1):
        question["id"] = f"Q{number:02d}"
        question["batch"] = (number - 1) // 10 + 1
        if question["unit"] == "USD":
            question["question"] += " Answer in whole US dollars."
        else:
            question["question"] += " Answer as a percentage to two decimal places."
    public = [{k: q[k] for k in ("id", "batch", "question", "unit")} for q in key]
    (HERE / "questions.json").write_text(json.dumps(public, indent=2) + "\n")
    (HERE / "answer_key.json").write_text(json.dumps(key, indent=2) + "\n")
    print(pd.DataFrame(key).groupby(["batch", "category"]).size().unstack(fill_value=0))


if __name__ == "__main__":
    main()
