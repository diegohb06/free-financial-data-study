"""Lay out the folders the answering agents work in, outside the repository.

Usage: prepare_run.py DIR

Creates DIR/raw (raw SEC companyfacts files), DIR/pipeline (our dataset),
DIR/questions (one file per batch), DIR/answers, and DIR/prompts (the exact
prompt for each condition and batch). The answer key is never copied.
"""

import csv
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "killtest"))

from common import companies  # noqa: E402
from groundtruth import sec  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1]).resolve()
    for name in ("raw", "pipeline", "questions", "answers", "prompts"):
        (out / name).mkdir(parents=True, exist_ok=True)

    names = {row["ticker"]: row["name"] for row in csv.DictReader(open(HERE / "names.csv"))}
    with open(out / "raw" / "index.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ticker", "company", "file", "note"])
        for company in companies():
            for cik, note in ((company["cik"], ""), (company["predecessor_cik"], "earlier filings, under the company's previous SEC registrant number")):
                if not cik:
                    continue
                name = f"CIK{int(cik):010d}.json"
                shutil.copy(sec.CACHE_DIR / f"data.sec.gov__api__xbrl__companyfacts__{name}", out / "raw" / name)
                writer.writerow([company["ticker"], names[company["ticker"]], name, note])

    for path in (HERE / "pipeline").iterdir():
        shutil.copy(path, out / "pipeline" / path.name)

    questions = json.loads((HERE / "questions.json").read_text())
    template = (HERE / "prompt.md").read_text()
    tools = json.loads((HERE / "conditions.json").read_text())
    for batch in sorted({q["batch"] for q in questions}):
        file = out / "questions" / f"batch{batch}.json"
        file.write_text(json.dumps([{k: q[k] for k in ("id", "question")} for q in questions if q["batch"] == batch], indent=2) + "\n")
        for condition, allowed in tools.items():
            prompt = (
                template.replace("{QUESTIONS_FILE}", str(file))
                .replace("{TOOLS}", allowed.replace("{DIR}", str(out)))
                .replace("{ANSWERS_FILE}", str(out / "answers" / f"{condition}_batch{batch}.json"))
            )
            (out / "prompts" / f"{condition}_batch{batch}.txt").write_text(prompt)
    print(f"prepared {out}")


if __name__ == "__main__":
    main()
