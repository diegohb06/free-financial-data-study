"""Grade the agents' answers against the answer key, in code.

An answer is correct if it is within the key's tolerance (0.5%; for
percentages, 0.5% or 0.05 percentage points). A wrong answer is classified by
comparing it with real figures it might have been confused with.

Writes graded.csv and summary.json to reports/agent-accuracy-test/.
"""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "reports" / "agent-accuracy-test"
CONDITIONS = {"A": "web search only", "B": "raw SEC companyfacts", "C": "Ground Truth pipeline data"}
CATEGORIES = ("lookup", "definition", "restatement", "point_in_time", "derived")
MATCH = 0.005
# Checked in this order; the first kind of real figure the wrong answer equals.
MISTAKES = ("restated_vs_original", "wrong_period", "wrong_definition")


def close(answer: float, target: float, tolerance: dict) -> bool:
    if abs(answer - target) <= tolerance.get("relative", MATCH) * abs(target):
        return True
    return abs(answer - target) <= tolerance.get("absolute_points", 0)


def grade(entry: dict, answer) -> tuple[bool, str]:
    """(correct, failure type) for one answer. Failure type is "" when correct."""
    if answer is None or isinstance(answer, (str, bool)) or not math.isfinite(answer):
        return False, "refused"
    if close(answer, entry["answer"], entry["tolerance"]):
        return True, ""
    for power in (3, 6, 9, 2, -2, -3, -6, -9):
        if close(answer * 10.0 ** power, entry["answer"], entry["tolerance"]):
            return False, "wrong_scale"
    for mistake in MISTAKES:
        if any(close(answer, value, {"relative": MATCH}) for value in entry["known_wrong_values"][mistake]):
            return False, mistake
    return False, "unmatched"


def wilson(correct: int, total: int) -> tuple[float, float]:
    """95% confidence interval for a proportion."""
    if total == 0:
        return 0.0, 0.0
    z, p = 1.96, correct / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return max(0.0, centre - half), min(1.0, centre + half)


def paired(first: np.ndarray, second: np.ndarray) -> dict:
    """Accuracy of first minus second on the same questions, with a bootstrap interval and exact sign test."""
    difference = first.astype(float) - second.astype(float)
    rng = np.random.default_rng(0)
    means = rng.choice(difference, size=(10_000, len(difference))).mean(axis=1)
    wins, losses = int((difference > 0).sum()), int((difference < 0).sum())
    discordant = wins + losses
    tail = sum(math.comb(discordant, k) for k in range(min(wins, losses) + 1)) / 2 ** discordant if discordant else 1.0
    return {
        "difference": float(difference.mean()),
        "ci95": [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))],
        "first_right_second_wrong": wins, "second_right_first_wrong": losses,
        "exact_p_value": min(1.0, 2 * tail),
    }


def rate(rows: pd.DataFrame) -> dict:
    correct, total = int(rows.correct.sum()), len(rows)
    low, high = wilson(correct, total)
    return {"correct": correct, "questions": total, "accuracy": correct / total if total else 0.0, "ci95": [low, high]}


def main() -> None:
    key = {entry["id"]: entry for entry in json.loads((HERE / "answer_key.json").read_text())}
    rows = []
    for condition in CONDITIONS:
        answers = {}
        for path in sorted((RESULTS / "answers").glob(f"{condition}_batch*.json")):
            answers.update({a["id"]: a for a in json.loads(path.read_text())})
        for identifier, entry in key.items():
            given = answers.get(identifier)
            answer = given.get("answer") if given else None
            correct, failure = grade(entry, answer)
            if given is None:
                failure = "not_answered"
            rows.append({
                "condition": condition, "id": identifier, "batch": entry["batch"], "category": entry["category"],
                "ticker": entry["ticker"], "item": entry["item"], "fiscal_year_end": entry["fiscal_year_end"],
                "basis": entry["basis"], "key": entry["answer"], "answer": answer,
                "correct": correct, "failure": failure,
            })
    graded = pd.DataFrame(rows)
    graded.to_csv(RESULTS / "graded.csv", index=False)

    summary = {"conditions": CONDITIONS, "accuracy": {}, "failures": {}, "comparisons": {}}
    for condition, group in graded.groupby("condition"):
        summary["accuracy"][condition] = {"all": rate(group)} | {
            category: rate(group[group.category == category]) for category in CATEGORIES
        }
        summary["failures"][condition] = group[~group.correct].failure.value_counts().to_dict()
    wide = graded.pivot(index="id", columns="condition", values="correct")
    category = graded.drop_duplicates("id").set_index("id").category
    for first, second in (("C", "B"), ("C", "A"), ("B", "A")):
        summary["comparisons"][f"{first}_minus_{second}"] = {"all": paired(wide[first].to_numpy(), wide[second].to_numpy())} | {
            name: paired(wide.loc[category == name, first].to_numpy(), wide.loc[category == name, second].to_numpy())
            for name in CATEGORIES
        }
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
