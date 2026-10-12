# Ground Truth dataset (50 companies, annual, fiscal years ending 2019 onward)

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
