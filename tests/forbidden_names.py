"""Denylist used by tests only. Production fixtures must not contain these strings."""

# Accounting / advisory firm names and common expense-product fingerprints.
# Word-boundary matching is applied by the test.
FIRM_AND_PRODUCT = [
    "Deloitte",
    "PricewaterhouseCoopers",
    "PwC",
    "KPMG",
    "Ernst & Young",
    "Ernst and Young",
    "Grant Thornton",
    "CohnReznick",
    "Baker Tilly",
    "Crowe",
    "BDO USA",
    "RSM US",
    "Moss Adams",
    "CliftonLarsonAllen",
    "Expensify",
    "Concur",
    "Chrome River",
    "Certify",
    "Emburse",
    "Bill.com",
    "NetSuite",
    "QuickBooks",
    "Xero",
    "Workday",
    "Coupa",
    "SAP Concur",
]

ALLOWED_PEOPLE = {
    "Bruce Wayne",
    "Peter Parker",
    "Clark Kent",
    "Diana Prince",
    "Tony Stark",
}

ALLOWED_ENTITIES = {
    "Wayne Enterprises LLC",
    "Daily Bugle Media LLC",
    "Stark Industries Holdings",
}

ALLOWED_PUBLIC_MERCHANTS = {"Amazon", "Uber", "Starbucks"}
