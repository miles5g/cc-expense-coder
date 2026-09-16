"""Plain data objects used across the pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Transaction:
    """One statement line after parsing / cleaning."""

    txn_id: str
    cardholder_raw: str
    cardholder_first: str
    txn_date: str  # ISO YYYY-MM-DD after clean
    post_date: str
    description_raw: str
    extended_details: str
    appears_as: str
    amount: int
    txn_type: str  # Charge | Credit | Payment
    country_raw: str
    country: str
    reference_number: str
    row_class: str  # CHARGE | CREDIT | PAYMENT
    entity: str = ""
    merchant_key: str = ""
    gl_code: str = ""
    gl_name: str = ""
    coding_source: str = ""  # reference | coa | review
    confidence: str = ""  # confident | review
    review_reason: str = ""
    origin_kept: bool = True

    def as_csv_row(self) -> dict[str, Any]:
        data = asdict(self)
        data["amount"] = str(self.amount)
        return data


@dataclass
class ChartAccount:
    gl_code: str
    name: str
    keywords: list[str] = field(default_factory=list)


@dataclass
class ReferenceRow:
    merchant_key: str
    gl_code: str
    times_seen: int
    appears_as: str


@dataclass
class EntityMapRow:
    first_name: str
    full_name: str
    entity: str


@dataclass
class JournalLine:
    gl_code: str
    debit: int
    credit: int
    description: str

    def as_csv_row(self) -> dict[str, Any]:
        return {
            "GL Code": self.gl_code,
            "Debit": "" if self.debit == 0 else str(self.debit),
            "Credit": "" if self.credit == 0 else str(self.credit),
            "Description": self.description,
        }


@dataclass
class EntityJournal:
    entity: str
    lines: list[JournalLine]
    debit_total: int
    credit_total: int
    balanced: bool
    excluded_review_amount: int = 0


@dataclass
class Reconciliation:
    period: str
    reported_activity: int
    cleaned_activity: int
    variance_vs_statement: int
    payment_rows_dropped: int
    payment_amount_dropped: int
    entity_nets: dict[str, int]
    entity_sum: int
    variance_entities_vs_cleaned: int
    review_count: int
    review_amount: int
    coded_amount: int
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "reported_activity": self.reported_activity,
            "cleaned_activity": self.cleaned_activity,
            "variance_vs_statement": self.variance_vs_statement,
            "payment_rows_dropped": self.payment_rows_dropped,
            "payment_amount_dropped": self.payment_amount_dropped,
            "entity_nets": self.entity_nets,
            "entity_sum": self.entity_sum,
            "variance_entities_vs_cleaned": self.variance_entities_vs_cleaned,
            "review_count": self.review_count,
            "review_amount": self.review_amount,
            "coded_amount": self.coded_amount,
            "notes": self.notes,
        }


@dataclass
class PipelineResult:
    cleaned: list[Transaction]
    origin: list[Transaction]
    by_entity: dict[str, list[Transaction]]
    coded: list[Transaction]
    review: list[Transaction]
    journals: dict[str, EntityJournal]
    reconciliation: Reconciliation
    reference_updated: list[ReferenceRow]
    dropped_payments: list[Transaction]
    card_payable_gl: str
    unmapped: list[Transaction] = field(default_factory=list)
