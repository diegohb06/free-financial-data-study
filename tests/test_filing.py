"""Tests for reading the SEC's rendered statement pages."""

from datetime import date

from groundtruth import filing
from groundtruth.parse import Version

SUMMARY = """<FilingSummary><MyReports>
<Report><HtmlFileName>R2.htm</HtmlFileName><MenuCategory>Statements</MenuCategory></Report>
<Report><HtmlFileName>R9.htm</HtmlFileName><MenuCategory>Notes</MenuCategory></Report>
<Report><MenuCategory>Statements</MenuCategory></Report>
<Report><HtmlFileName>R3.htm</HtmlFileName><MenuCategory>Uncategorized</MenuCategory>
<LongName>100010002 - Statement - Consolidated Statements Of Income</LongName></Report>
</MyReports></FilingSummary>"""

PAGE = """<table><tr><th class="tl" colspan="1"><div><strong>INCOME - USD ($)<br> shares in Thousands, $ in Millions</strong></div></th></tr>
<tr class="re"><td class="pl"><a onclick="Show.showAR( this, 'defref_us-gaap_Revenues', window );">Revenue</a></td>
<td class="nump">$ 6,666.5<span></span></td><td class="nump">5,856.7<span></span></td></tr>
<tr class="ro"><td class="pl"><a onclick="Show.showAR( this, 'defref_us-gaap_NetIncomeLoss', window );">Net loss</a></td>
<td class="num">(1,489.3)<span></span></td><td class="text">&#160;</td></tr>
<tr class="re"><td class="pl"><a onclick="Show.showAR( this, 'defref_us-gaap_EarningsPerShareDiluted', window );">EPS</a></td>
<td class="nump">$ 2.97<span></span></td></tr></table>"""


def test_only_primary_statement_pages_are_listed():
    # R3 is a real statement that the SEC's summary files under "Uncategorized".
    assert filing.statement_pages(SUMMARY) == ["R2.htm", "R3.htm"]


def test_values_are_scaled_by_the_dollar_scale_not_the_share_scale():
    values = filing.page_values(PAGE, "Revenues")
    assert filing.on_face(values, 6_666_500_000)
    assert filing.on_face(values, 5_856_700_000)
    assert not filing.on_face(values, 6_666_500)


def test_parentheses_are_negative_and_sign_is_ignored_when_matching():
    values = filing.page_values(PAGE, "NetIncomeLoss")
    assert -1_489_300_000 in values
    assert filing.on_face(values, -1_489_300_000)


def test_per_share_values_match_unscaled():
    assert filing.on_face(filing.page_values(PAGE, "EarningsPerShareDiluted"), 2.97)


def test_a_tag_that_is_not_on_the_page_matches_nothing():
    assert filing.page_values(PAGE, "Assets") == []
    assert not filing.on_face([], 100)


def version(tag, val, accn, filed):
    return Version(tag, date(2021, 12, 31), val, accn, "10-K", date.fromisoformat(filed))


def with_statements(monkeypatch, shown):
    """Pretend each (filing, tag) shows the given numbers on its primary statements."""
    monkeypatch.setattr(filing, "face_values", lambda ciks, accn, tag: shown.get((accn, tag), []))


def test_the_tag_on_the_statement_is_chosen_over_a_higher_priority_tag_in_the_notes(monkeypatch):
    with_statements(monkeypatch, {("A-21", "ContractRevenue"): [100.0]})
    notes_only = [version("Revenues", 105, "A-21", "2022-02-15")]
    on_statement = [version("ContractRevenue", 100, "A-21", "2022-02-15")]
    history, found = filing.statement_history([1], [notes_only, on_statement])
    assert found and [v.tag for v in history] == ["ContractRevenue"]


def test_a_changed_value_counts_only_if_it_is_on_the_later_statement(monkeypatch):
    history = [
        version("Revenues", 100, "A-21", "2022-02-15"),
        version("Revenues", 80, "A-22", "2023-02-15"),   # recast, on the statement
        version("Revenues", 115, "A-23", "2024-02-15"),  # segment total in a note
    ]
    with_statements(monkeypatch, {("A-21", "Revenues"): [100.0], ("A-22", "Revenues"): [80.0]})
    kept, found = filing.statement_history([1], [history])
    assert found and [v.val for v in kept] == [100, 80]


def test_a_value_never_seen_on_a_statement_is_reported_as_unconfirmed(monkeypatch):
    with_statements(monkeypatch, {})
    history = [version("Revenues", 100, "A-21", "2022-02-15"), version("Revenues", 80, "A-22", "2023-02-15")]
    kept, found = filing.statement_history([1], [history])
    assert not found and [v.val for v in kept] == [100]
