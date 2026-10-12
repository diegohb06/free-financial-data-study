"""Check a value against the face of the financial statements in a filing.

The SEC renders every XBRL filing as numbered "R" pages and lists them in
FilingSummary.xml, marking which pages are primary statements and which are
notes. A tag can appear in both with different meanings (for example segment
revenue including sales between segments), so a value only counts as a
restated figure if it sits on a primary statement.
"""

import functools
from concurrent.futures import ThreadPoolExecutor
import re
import xml.etree.ElementTree as ET

import requests

from . import sec

SCALES = {"thousands": 1e3, "millions": 1e6, "billions": 1e9}


def statement_pages(summary_xml: str) -> list[str]:
    """File names of the primary-statement pages listed in FilingSummary.xml."""
    pages = []
    for report in ET.fromstring(summary_xml).iter("Report"):
        # MenuCategory is sometimes "Uncategorized" for a real statement; the
        # long name always says "- Statement -".
        is_statement = (report.findtext("MenuCategory") or "") == "Statements" or " - Statement - " in (
            report.findtext("LongName") or ""
        )
        if is_statement and report.findtext("HtmlFileName"):
            pages.append(report.findtext("HtmlFileName"))
    return pages


def _number(text: str) -> float | None:
    cleaned = re.sub(r"<[^>]+>", "", text).replace("$", "").replace(",", "").strip()
    negative = cleaned.startswith("(")
    cleaned = cleaned.strip("()").strip()
    try:
        return -float(cleaned) if negative else float(cleaned)
    except ValueError:
        return None


def page_values(html: str, tag: str) -> list[float]:
    """Every number shown for a us-gaap tag on one R page, in whole units."""
    header = re.search(r"<th[^>]*class=\"tl\"[^>]*>(.*?)</th>", html, re.S)
    scale = 1.0
    if header:
        # "shares in Thousands, $ in Millions": the dollar scale is the one that counts.
        match = re.search(r"\$\s*in\s*(thousands|millions|billions)", header.group(1), re.I) or re.search(
            r"in\s*(thousands|millions|billions)", header.group(1), re.I
        )
        if match:
            scale = SCALES[match.group(1).lower()]
    values = []
    for row in re.findall(r"<tr.*?</tr>", html, re.S):
        if f"defref_us-gaap_{tag}'" not in row:
            continue
        for cell in re.findall(r"<td[^>]*class=\"nump?\"[^>]*>(.*?)</td>", row, re.S):
            number = _number(cell)
            if number is not None:
                # Per-share rows are shown unscaled even on a scaled page.
                values.extend([number * scale, number])
    return values


def on_face(values: list[float], val: float) -> bool:
    """Whether a value matches one shown on the page, allowing for display rounding."""
    return any(abs(abs(shown) - abs(val)) <= max(0.0006 * abs(val), 0.005) for shown in values)


@functools.lru_cache(maxsize=None)
def _statement_html(cik: int, folder: str) -> tuple[str, ...] | None:
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}"
    try:
        pages = statement_pages(sec.get_text(f"{base}/FilingSummary.xml"))
    except requests.HTTPError:
        return None
    return tuple(sec.get_text(f"{base}/{page}") for page in pages)


def warm(filings: list[tuple[int, str]], workers: int = 8) -> None:
    """Download the statement pages of many filings in parallel (the SEC answers slowly)."""
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(lambda f: _statement_html(f[0], f[1].replace("-", "")), filings))


def face_values(ciks: list[int], accession: str, tag: str) -> list[float] | None:
    """Numbers shown for a tag on a filing's primary statements; None if the filing has no R pages."""
    for cik in ciks:
        pages = _statement_html(cik, accession.replace("-", ""))
        if pages is not None:
            return [value for html in pages for value in page_values(html, tag)]
    return None


def statement_history(ciks: list[int], candidates: list[list]) -> tuple[list, bool]:
    """Pick the tag a company uses on its statements, and that tag's confirmed versions.

    candidates holds one version history per candidate tag, in priority order,
    all for the same fiscal year. The chosen tag is the first whose original
    value appears on a primary statement of the original filing. Its later
    versions are kept only if they repeat the previous value or also appear on
    a primary statement of their own filing.

    Returns the confirmed versions and whether the original value was found on
    a statement. If it was not, the top-priority original is returned alone.
    """
    earliest = min(history[0].filed for history in candidates)
    originals = [history for history in candidates if history[0].filed == earliest]
    for history in originals:
        first = history[0]
        shown = face_values(ciks, first.accn, first.tag)
        if shown is None or not on_face(shown, first.val):
            continue
        kept = [first]
        for version in history[1:]:
            if abs(version.val - kept[-1].val) > 0.001 * abs(kept[-1].val):
                shown = face_values(ciks, version.accn, version.tag)
                if shown is None or not on_face(shown, version.val):
                    continue
            kept.append(version)
        return kept, True
    return originals[0][:1], False
