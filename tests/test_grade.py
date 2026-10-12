"""Tests for grading agent answers."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agenttest"))

import grade  # noqa: E402

ENTRY = {
    "answer": 78_740_000_000.0, "tolerance": {"relative": 0.005},
    "known_wrong_values": {
        "restated_vs_original": [93_775_000_000.0],
        "wrong_period": [79_990_000_000.0],
        "wrong_definition": [52_080_000_000.0],
    },
}
PERCENT = {
    "answer": 4.0325, "tolerance": {"relative": 0.005, "absolute_points": 0.05},
    "known_wrong_values": {"restated_vs_original": [], "wrong_period": [3.95], "wrong_definition": []},
}


def test_within_half_a_percent_is_correct():
    assert grade.grade(ENTRY, 78_740_000_000) == (True, "")
    assert grade.grade(ENTRY, 78_700_000_000) == (True, "")  # rounded to the nearest 100 million
    assert grade.grade(ENTRY, 79_200_000_000)[0] is False  # 0.58% off


def test_no_answer_is_a_refusal():
    assert grade.grade(ENTRY, None) == (False, "refused")
    assert grade.grade(ENTRY, "about 78 billion") == (False, "refused")


def test_wrong_answers_are_matched_to_the_figure_they_were_confused_with():
    assert grade.grade(ENTRY, 93_775_000_000) == (False, "restated_vs_original")
    assert grade.grade(ENTRY, 79_990_000_000) == (False, "wrong_period")
    assert grade.grade(ENTRY, 52_080_000_000) == (False, "wrong_definition")
    assert grade.grade(ENTRY, 61_000_000_000) == (False, "unmatched")


def test_the_right_number_in_the_wrong_units_is_wrong():
    assert grade.grade(ENTRY, 78_740) == (False, "wrong_scale")  # given in millions
    assert grade.grade(PERCENT, 0.040325) == (False, "wrong_scale")  # a fraction, not a percentage


def test_percentages_allow_five_hundredths_of_a_point():
    assert grade.grade(PERCENT, 4.03) == (True, "")
    assert grade.grade(PERCENT, 4.08) == (True, "")
    assert grade.grade(PERCENT, 4.10)[0] is False
    assert grade.grade(PERCENT, 3.95) == (False, "wrong_period")


def test_wilson_interval():
    low, high = grade.wilson(8, 10)
    assert round(low, 3) == 0.490 and round(high, 3) == 0.943
    assert grade.wilson(10, 10)[1] == 1.0


def test_paired_comparison_counts_disagreements():
    first = np.array([True, True, True, False, True])
    second = np.array([True, False, False, False, True])
    result = grade.paired(first, second)
    assert result["difference"] == 0.4
    assert (result["first_right_second_wrong"], result["second_right_first_wrong"]) == (2, 0)
    assert result["exact_p_value"] == 0.5
