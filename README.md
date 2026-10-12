# How good is free financial data? Four tests

**Author: Diego Bermea.** October 2026.

**Headline: dating a company's results by the day the fiscal period ended, instead of the day they were filed with the SEC, inflated a value backtest on S&P 500 companies by about 2.2% a year. Waiting two months after each quarter end before using the numbers removed the inflation entirely.**

This repository holds four tests of free fundamental data (the SEC's own XBRL data, and free websites built on it), the code that ran them, and the result files behind every number below.

> **Data, not investment advice.** Everything here describes historical data and its measurement. Nothing is a recommendation to buy, sell or hold any security. Backtest returns are hypothetical, ignore trading costs, and are inflated by survivorship bias (explained below). Do not quote them as strategy performance.

## Why these tests were run

The starting idea was that free financial data is unreliable enough that a verified, point-in-time dataset would be worth building: one where every number links to its SEC filing, says exactly what it counts, and keeps every version as first reported and as later revised.

Each test was designed so that it could kill that idea. Mostly, they did. Free data turned out to be accurate, restatements turned out to be rare, and an AI agent answered questions just as well from raw SEC files. One real effect was found, in timing, and it has a cheap fix.

## Summary

| Test | Question | Result |
| --- | --- | --- |
| 1. Pilot, 10 companies | Is free data full of errors? | No. 0 wrong values in 90. Differences were unlabeled definitions and one restatement |
| 2. 50 companies | How often are values restated, how often does a free source differ, and does it change a backtest? | 2.5% of values restated by more than 1%. 7.2% differ from the free source by definition. 0 true errors. No measurable effect on backtest returns |
| 3. Timing, S&P 500 | Does dating results by period end instead of filing date change a backtest? | Yes for a value screen: +2.2% a year (95% confidence interval 1.3% to 3.1%). No for revenue growth. Gone with a two-month lag |
| 4. AI agent, 60 questions | Does an AI agent answer more accurately from cleaned data than from raw SEC data? | No. 60 of 60 from both. 59 of 60 from web search alone |

## Test 3: timing look-ahead (the headline)

A quarter that ends on March 31 is not public on March 31. The median S&P 500 company in this data filed its report 35 days after the period ended (25 days at the fast end, 54 at the slow end). A backtest that reads a table keyed by period date, with no lag, is using numbers nobody had yet.

**What was tested.** Two versions of the same strategies, using identical numbers. The only difference is when each quarter's results are treated as known:

- **Period-end version:** known on the fiscal period end date.
- **Filing-date version:** known only from the date the 10-Q or 10-K was filed with the SEC.

| | |
| --- | --- |
| Companies | The 500 S&P 500 members as of October 11, 2026. 490 had usable data |
| Data | Quarterly, from 10-Q and 10-K filings: 30,079 company-quarters |
| Screens | Earnings yield (trailing twelve-month net income divided by market value) and revenue growth (trailing twelve months against a year earlier) |
| Portfolio | Top fifth of ranked companies, equally weighted. Also long-short: top fifth minus bottom fifth |
| Rebalancing | Quarterly on calendar quarter ends, March 2012 to March 2026: 57 quarters |

**Results.** Return of the period-end version minus the filing-date version, per year.

| Screen | Portfolio | Difference | 95% confidence interval | Quarters period-end was ahead | Smallest effect the test could reliably detect |
| --- | --- | --- | --- | --- | --- |
| Earnings yield | Top fifth | +2.2% | +1.3% to +3.1% | 82% | 1.3% |
| Earnings yield | Long-short | +4.7% | +3.2% to +6.2% | 84% | 2.1% |
| Revenue growth | Top fifth | +0.1% | −1.2% to +1.3% | 51% | 1.8% |
| Revenue growth | Long-short | −0.3% | −2.3% to +1.5% | 51% | 2.7% |

"Reliably detect" means the effect size that this many quarters, with this much quarter-to-quarter variation, would flag as significant 80% of the time at the 5% level.

**A lag removes it.**

| Rebalance date | Same picks in both versions | Earnings yield, top fifth | Earnings yield, long-short |
| --- | --- | --- | --- |
| On the quarter end | 85% | +2.2% (+1.3% to +3.1%) | +4.7% (+3.2% to +6.2%) |
| One month later | 87% | +0.6% (−0.1% to +1.4%) | +1.8% (+0.6% to +3.1%) |
| Two months later | 98% | −0.1% (−0.4% to +0.3%) | −0.2% (−0.8% to +0.4%) |

By two months after quarter end almost every S&P 500 company has filed, so both versions see the same numbers.

**It holds up in subsamples.** The top-fifth earnings yield difference was +1.9% a year in 2012–2018 (0.9% to 3.0%), +2.5% in 2019–2026 (1.1% to 3.8%), and +2.2% (1.1% to 3.3%) using only the 284 companies that were already in the index before the test period began.

**Limits of this test.**

- **Survivorship bias.** The companies are today's index members. Companies that failed, were acquired or dropped out since 2012 are missing. This inflates the return levels of both versions (the earnings yield top fifth returned 18.8% a year in one and 16.6% in the other; neither is a realistic strategy return). It affects the difference much less, because both versions pick from the same pool. But failed companies are where knowing bad earnings early would matter most, so the true bias could be larger. Testing that needs historical index membership, which is not free.
- **Filing date is not announcement date.** Most companies announce earnings in a press release before filing. On a quarter end this hardly matters, since the quarter has been neither announced nor filed. For the one-month-later row it does, so the true bias there is probably smaller than shown.
- **No trading costs,** equal weights, no turnover limits. These apply equally to both versions.
- **Values were not confirmed against the face of the statements** as they were in test 2. The same tag choice is used in both versions, so a wrong tag adds noise without favoring either.
- **Coverage is thinner early on,** especially for revenue (178 companies ranked in 2012 against 473 by the end), because older filings used revenue tags the code does not map.
- **The confidence intervals treat quarters as independent.**
- **Restatements are deliberately left out.** Both versions use figures as first filed, so timing is the only thing measured.

## Test 1: 10-company pilot

Revenue and net income for fiscal 2021–2025, from the SEC's XBRL data, compared with StockAnalysis.com. Coca-Cola's SEC data did not load and was excluded, leaving 9 companies and 90 values.

- **True wrong values: 0.**
- **Mismatches over 1%: 17 of 90**, of which 15 came from two companies whose free-site figures use a different, unlabeled definition. JPMorgan's free-site revenue is net of the provision for credit losses, and its net income is the figure available to common stockholders. ExxonMobil's free-site revenue appears to exclude other income (not confirmed).
- **Restatement: 2 of 90.** Johnson & Johnson's fiscal 2021 revenue was first reported as $93,775M and later recast to $78,740M after the Kenvue spin-off. The free site showed only the recast figure.
- Microsoft, Apple, NVIDIA, Walmart and Intel matched exactly, 50 of 50.

**Limits.** This pilot was run by hand in a chat session with a web-fetch tool, so there is no code for it in this repository. Mismatches were re-fetched and checked; matches were not. All ten companies are very large, which is where data is cleanest. Test 2 was designed to fix these weaknesses.

## Test 2: 50 companies

50 companies (20 large, 15 mid, 15 small, including 6 banks and 6 energy companies; listed with reasons in `killtest/companies.csv`), 10 line items across all three statements, fiscal years ending 2019 through 2025, annual figures. 3,185 values measured, each confirmed on the face of a financial statement in the SEC's rendered copy of the original filing.

**Restatements: first reported versus latest.**

| Change | Values | Share of 3,174 |
| --- | --- | --- |
| Any change at all | 179 | 5.6% |
| More than 0.1% | 105 | 3.3% |
| More than 1% | 79 | 2.5% |
| More than 5% | 51 | 1.6% |

These leave out 11 earnings-per-share values that changed only because of a stock split.

Restatements were concentrated in the largest companies (4.6% of large-company values against 1.0% for mid and 1.2% for small), and in a few names: GE (29), Pfizer (10) and AT&T (9) account for 61% of them. The pattern looks like spin-offs and divestitures, where prior years are recast to remove the business that left. That cause is inferred from the pattern; each filing's explanation was not read. The largest was GE's fiscal 2022 revenue, first reported as $76.6B and now $29.1B.

**Comparison with a free source** (Yahoo Finance through the `yfinance` library; fiscal 2022–2025; 1,730 values).

| Result | Values | Share |
| --- | --- | --- |
| Match (within 0.1%) | 1,541 | 89.1% |
| Small difference (0.1% to 1%) | 29 | 1.7% |
| Definition difference | 124 | 7.2% |
| Shows the first-reported figure where the company has since restated | 2 | 0.1% |
| Unexplained | 34 | 2.0% |
| True error (wrong scale, wrong sign) | 0 | 0% |

A definition difference means the free source's number can be rebuilt exactly from other SEC figures. It is a different quantity under the same label, not a mistake. 64 of the 124 are operating income, where the free source shows its own standardized calculation. Others include capital expenditure that adds software purchases, and bank cash that includes deposits at other banks.

**Backtest: point-in-time versus restated.** Each quarter from June 2021 to March 2026, hold the 10 companies with the highest revenue growth, once using revenue as known on that date and once using today's figures. The picks differed in 3 of 20 quarters. Return difference: +0.2% a year (95% confidence interval −1.2% to +1.7%). No measurable effect.

**Other things it turned up.**

- **A tag does not say where a number comes from.** A first pass found 108 values restated by more than 1%. After checking each against the face of the statements and excluding proxy statements, 90 were real (79 plus the 11 stock splits). The false ones were figures like segment revenue in a note, tagged with the same revenue tag.
- **One error in SEC data itself.** Universal Corporation's 2026 proxy statement tags five years of net income at one-thousandth of the real amount (`reports/kill-test-full/filer_errors.csv`).
- **Companies change SEC identity.** ExxonMobil and APA file under new registrant numbers; their history sits under the old ones.

**Limits.** The 50 companies were chosen by judgement, not at random, and all still exist today. Johnson & Johnson was included knowing it had restated (without it the rate is 2.4%, not 2.5%). A restatement is counted only when the company kept the same tag, so the rate is if anything understated. The 34 unexplained differences may be further definition differences or errors; this test cannot tell which. Definition differences were classified automatically and the filings were not read to confirm each one. 50 values were excluded because the tagged number was not found on a statement, 19 of them from Alaska Air, which suggests a parsing gap. The backtest sample (50 companies, 20 quarters) is small, and a growth-rate screen is unusually insensitive to recasts because both years are usually rewritten together; a screen on levels was not tested.

## Test 4: AI-agent accuracy

60 questions with known numeric answers, in five categories: plain lookups, definition-sensitive, restatement (first reported versus latest), point-in-time (what was known on a date) and derived (calculated from two figures). Each was answered three ways by the same AI model (Claude Opus 5.5, run as subagents in Claude Code) with the same instructions, differing only in the tools allowed.

| Condition | Correct | 95% confidence interval |
| --- | --- | --- |
| A: web search only | 59 of 60 | 91% to 100% |
| B: raw SEC companyfacts files only | 60 of 60 | 94% to 100% |
| C: prepared dataset with definitions, versions, filing dates and source links | 60 of 60 | 94% to 100% |

The prepared dataset gave no accuracy advantage. The single miss was a web-search answer that took Alcoa's 2025 net income from the earnings press release ($1,170M) where the 10-K says $1,157M. The prepared dataset did take fewer tool calls and less time, but that was not what the test was designed to measure and the gap over raw SEC data was small.

**Safeguards.** The questions and answer key were generated with a fixed random seed and committed before any agent ran. Grading is done in code (`agenttest/grade.py`): correct means within 0.5% of the key. The answer key was removed from the working folder while the agents ran.

**Limits.**

- **Tool limits were by instruction, not enforced.** Every agent's tool calls were audited afterward and all complied, but this is weaker than a technical restriction.
- **The questions spell out the definition, period and version.** That makes them gradable, but removes the ambiguity that causes mistakes in practice. Vaguer questions were not tested.
- **The web condition is not a weak baseline.** Those agents read SEC filings directly, and in one batch said some figures were recalled from memory.
- **The answer key comes from the prepared dataset,** so condition C agreeing with it is expected. The informative result is that A and B agree too.
- **One strong model, one run per question, 50 companies, annual data.** A weaker or cheaper model might show a gap. This was not tested.
- **Not exactly reproducible.** Language model output varies from run to run. The questions, key, prompts, all 180 answers and the grader are included so the grading can be checked.

## What didn't work

- **"Free data is full of errors."** Not supported. 0 true errors in 90 values, then 0 in 1,730.
- **"Restatements quietly break backtests."** Restatements over 1% affect 2.5% of values and moved backtest returns by nothing measurable.
- **"AI agents need cleaned data to answer accurately."** Not on explicit questions with a strong model.
- **The timing effect is real but easy to avoid.** Filing dates are in the free SEC data, and a two-month lag removes the bias without them.

What did hold up: labels on free sites hide definition choices fairly often (7.2% of values compared), and the timing of when a number became public matters for value screens.

## Reproducing the results

Python 3.12 was used.

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Set your SEC User-Agent.** The SEC requires automated clients to identify themselves with a name and contact email. The code reads this from the `SEC_USER_AGENT` environment variable and refuses to download without it:

```
export SEC_USER_AGENT="Your Name you@example.com"
```

Add that line to `~/.zshrc` or `~/.bashrc` to keep it between sessions. Do not commit your email to the repository. Requests are limited to 5 a second (the SEC allows 10) and every response is cached in `cache/`, which is not committed.

**Run the tests.**

```
PYTHONPATH=. .venv/bin/python -m pytest tests
```

49 tests. Four of them check figures against real filings (for example Apple's fiscal 2022 revenue of $394,328M) and are skipped until the SEC cache exists.

**Run the analyses,** all with `PYTHONPATH=.`:

| Test | Commands | First run downloads |
| --- | --- | --- |
| 2 | `killtest/restatements.py`, `killtest/compare_free.py`, `killtest/backtest.py`, `killtest/summarize.py`, in that order | About 3,400 SEC pages |
| 3 | `killtest/timing.py` | About 500 SEC company files (roughly 1.7 GB) and 15 years of prices |
| 4 | `agenttest/build_dataset.py`, `agenttest/build_questions.py`, then `agenttest/grade.py` to re-grade the saved answers | Nothing new after test 2 |

Results will not match to the last digit. The SEC adds filings daily, Yahoo Finance revises adjusted prices and carries only the latest four fiscal years, and the S&P 500 list in `killtest/sp500.csv` is fixed at October 11, 2026.

## What is in this repository

| Path | Contents |
| --- | --- |
| `groundtruth/` | SEC download and cache, tag definitions, version tracking, statement-face checks, trailing-twelve-month figures |
| `killtest/` | Scripts for tests 2 and 3, the 50-company list, the S&P 500 list |
| `agenttest/` | Test 4: questions, answer key, prompts, the prepared dataset, the grader |
| `tests/` | The test suite |
| `reports/kill-test-full/` | Test 2 results: every value with its SEC accession number, every comparison and its classification, backtest quarters |
| `reports/kill-test-timing/` | Test 3 results: every quarter of every test, and the summary |
| `reports/agent-accuracy-test/` | Test 4 results: all 180 answers with each agent's stated source, grades, summary |

"Kill test" is the name used for a test designed to decide whether to drop the idea.

**Not included:** the SEC response cache, and any raw data from Yahoo Finance. The comparison file records our SEC-derived value, the size of the difference and its classification, not the free source's figures. Price data appears only as computed portfolio returns.

## Data sources

- **SEC EDGAR** XBRL data and rendered filings (`data.sec.gov`, `www.sec.gov`). Public.
- **Yahoo Finance** through the `yfinance` library, for the free-source comparison and for prices. Subject to Yahoo's terms; not redistributed here.
- **StockAnalysis.com,** for the pilot comparison only.
- **Wikipedia,** "List of S&P 500 companies", for `killtest/sp500.csv`. That file is derived from Wikipedia and is under CC BY-SA 4.0.

## How this was made

The tests were designed and directed by Diego Bermea. The code was written and run with Claude Code (Anthropic's coding assistant).

## License

- **Code:** MIT. See `LICENSE`.
- **This write-up and the result files in `reports/`:** [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/). Credit "Diego Bermea".
- `killtest/sp500.csv` is under CC BY-SA 4.0, as noted above.

## Disclaimer

This is a data study, not investment advice. It is provided for information and research only, with no warranty of accuracy or completeness. Nothing here is a recommendation about any security or strategy. Past and hypothetical returns do not predict future results. Check any figure against the original SEC filing before relying on it.
