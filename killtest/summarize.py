"""Kill test, part 4: the headline numbers, computed from the result files.

Writes reports/kill-test-full/summary.json. Every figure in the written report
comes from this file or from backtest_summary.json.
"""

import json

import pandas as pd

from common import RESULTS

THRESHOLDS = {"any": 0.0, "over_0.1pct": 0.001, "over_1pct": 0.01, "over_5pct": 0.05}


def rates(change: pd.Series) -> dict:
    return {"values": len(change)} | {
        name: {"count": int((change > t).sum()), "share": round(float((change > t).mean()), 4)}
        for name, t in THRESHOLDS.items()
    }


def main() -> None:
    values = pd.read_csv(RESULTS / "restatements.csv")
    usable = values[values.first_is_original & values.on_statement].copy()
    usable["change"] = usable.rel_diff.abs()

    # A stock split rewrites earnings per share without changing earnings.
    income = usable[usable["item"] == "NetIncome"].set_index(["ticker", "fiscal_year_end"]).change
    keys = list(zip(usable.ticker, usable.fiscal_year_end))
    usable["split"] = (
        (usable["item"] == "EPSDiluted") & (usable.change > 0.2)
        & pd.Series([income.get(key, 0.0) <= 0.01 for key in keys], index=usable.index)
    )
    core = usable[~usable.split]
    restated = core[core.change > 0.01]
    by_company = restated.groupby("ticker").size().sort_values(ascending=False)

    summary = {
        "restatements": {
            "companies": int(values.ticker.nunique()),
            "values_extracted": len(values),
            "excluded_not_on_a_primary_statement": int((~values.on_statement).sum()),
            "excluded_original_filing_not_available": int((values.on_statement & ~values.first_is_original).sum()),
            "values_measured": len(usable),
            "values_with_a_later_version": int((usable.n_versions > 1).sum()),
            "all_values": rates(usable.change),
            "stock_split_eps_values": int(usable.split.sum()),
            "excluding_stock_splits": rates(core.change),
            "excluding_stock_splits_and_fiscal_2025": rates(core[core.fiscal_year_end < "2025-01-01"].change),
            "excluding_stock_splits_and_jnj": rates(core[core.ticker != "JNJ"].change),
            "by_size": {size: rates(rows.change) for size, rows in core.groupby("size")},
            "by_item": {item: rates(rows.change) for item, rows in core.groupby("item")},
            "by_fiscal_year_ending": {year: rates(rows.change) for year, rows in core.groupby(core.fiscal_year_end.str[:4])},
            "companies_with_a_restatement_over_1pct": int(by_company.size),
            "restatements_over_1pct_by_company": by_company.to_dict(),
            "share_from_top_3_companies": round(float(by_company.head(3).sum() / max(len(restated), 1)), 4),
            "median_size_of_restatements_over_1pct": round(float(restated.change.median()), 4),
            "revenue_restated_over_1pct": rates(core[core["item"] == "Revenue"].change)["over_1pct"],
        }
    }

    compared = pd.read_csv(RESULTS / "comparison.csv")
    different = compared[~compared.result.isin(["match", "small difference"])]
    definitions = compared[compared.result == "definition difference"]
    hidden = compared[compared.restated_over_1pct & compared.result.isin(["match", "small difference"])]
    affected = compared[compared.restated_over_1pct | (compared.result == "definition difference")]
    summary["free_source_comparison"] = {
        "values_compared": len(compared),
        "companies": int(compared.ticker.nunique()),
        "fiscal_years_ending": sorted(compared.fiscal_year_end.str[:4].unique().tolist()),
        "results": compared.result.value_counts().to_dict(),
        "mismatch_over_1pct_share": round(len(different) / len(compared), 4),
        "definition_difference_share": round(len(definitions) / len(compared), 4),
        "companies_with_a_definition_difference": int(definitions.ticker.nunique()),
        "definition_differences_by_item": definitions.groupby("item").size().to_dict(),
        "unexplained_by_item": compared[compared.result == "unexplained"].groupby("item").size().to_dict(),
        "results_by_size": {
            size: rows.result.value_counts().to_dict() for size, rows in compared.groupby("size")
        },
        "restated_over_1pct_among_compared": int(compared.restated_over_1pct.sum()),
        "restated_where_free_source_shows_only_the_new_figure": len(hidden),
        "restated_or_definition_difference": {
            "count": len(affected), "share": round(len(affected) / len(compared), 4)
        },
    }
    errors = RESULTS / "filer_errors.csv"
    summary["filer_errors_in_proxy_statements"] = len(pd.read_csv(errors)) if errors.exists() else 0

    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
