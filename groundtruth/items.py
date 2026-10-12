"""The core line items of the kill test and the XBRL tags that can carry them.

Tags are listed in priority order: when one filing reports several of them for
the same period, the first in the list is used. `alternatives` are tags with a
different meaning that free sources sometimes show under the same label; they
are never used as our value, only to explain a mismatch.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Item:
    name: str
    statement: str
    kind: str  # "duration" (a full fiscal year) or "instant" (fiscal year end)
    unit: str
    tags: tuple[str, ...]
    definition: str
    alternatives: tuple[str, ...] = field(default=())


ITEMS = (
    Item(
        "Revenue", "income", "duration", "USD",
        (
            "Revenues",
            "RevenuesNetOfInterestExpense",
            "RegulatedAndUnregulatedOperatingRevenue",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet",
        ),
        "Total revenue as the company itself totals it on the income statement.",
        (
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueGoodsNet",
            "InterestAndDividendIncomeOperating",
            "RegulatedAndUnregulatedOperatingRevenue",
            "OperatingLeasesIncomeStatementLeaseRevenue",
        ),
    ),
    Item(
        "OperatingIncome", "income", "duration", "USD",
        ("OperatingIncomeLoss",),
        "Operating income as reported. Not reported by banks and some others.",
        (
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        ),
    ),
    Item(
        "NetIncome", "income", "duration", "USD",
        ("NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss"),
        "Net income attributable to the parent company. Where a company does not tag "
        "that, net income available to common shareholders, then net income including "
        "noncontrolling interests; the tag used is recorded with every value.",
        (
            "ProfitLoss",
            "NetIncomeLossAvailableToCommonStockholdersBasic",
            "NetIncomeLossAvailableToCommonStockholdersDiluted",
            "IncomeLossFromContinuingOperations",
        ),
    ),
    Item(
        "EPSDiluted", "income", "duration", "USD/shares",
        ("EarningsPerShareDiluted",),
        "Diluted earnings per share as reported (not adjusted for later stock splits).",
        ("EarningsPerShareBasic", "IncomeLossFromContinuingOperationsPerDilutedShare"),
    ),
    Item(
        "TotalAssets", "balance", "instant", "USD",
        ("Assets",),
        "Total assets.",
    ),
    Item(
        "TotalLiabilities", "balance", "instant", "USD",
        ("Liabilities",),
        "Total liabilities, only where the company reports the total itself.",
    ),
    Item(
        "StockholdersEquity", "balance", "instant", "USD",
        ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
        "Equity attributable to the parent company's shareholders. Where a company "
        "only tags total equity including noncontrolling interests, that is used and recorded.",
        ("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",),
    ),
    Item(
        "Cash", "balance", "instant", "USD",
        (
            "CashAndCashEquivalentsAtCarryingValue",
            "CashAndDueFromBanks",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ),
        "Cash and cash equivalents on the balance sheet, excluding restricted cash. "
        "Where a company only tags the total including restricted cash, that is used and recorded.",
        (
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "CashCashEquivalentsAndShortTermInvestments",
            "CashAndDueFromBanks",
        ),
    ),
    Item(
        "OperatingCashFlow", "cashflow", "duration", "USD",
        (
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ),
        "Net cash from operating activities. Where a company only tags the "
        "continuing-operations figure, that is used and recorded.",
        ("NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",),
    ),
    Item(
        "CapEx", "cashflow", "duration", "USD",
        (
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
            "PaymentsToExploreAndDevelopOilAndGasProperties",
        ),
        "Cash paid for property, plant and equipment, as a positive number. Not "
        "mapped for banks and real estate companies, which do not report it this way.",
        (
            "PaymentsToAcquireProductiveAssets",
            "PaymentsToAcquireOtherPropertyPlantAndEquipment",
            "PaymentsToAcquireOilAndGasPropertyAndEquipment",
            "PaymentsToAcquireRealEstate",
        ),
    ),
)

ITEMS_BY_NAME = {item.name: item for item in ITEMS}

# Banks tag fee income as contract revenue; it is a part of revenue, not the total.
BANK_REVENUE_TAGS = ("Revenues", "RevenuesNetOfInterestExpense")


def tags_for(item: Item, sector: str) -> tuple[str, ...]:
    """The tags that may carry an item for a company in a given sector."""
    if item.name == "Revenue" and sector == "Banks":
        return BANK_REVENUE_TAGS
    return item.tags
