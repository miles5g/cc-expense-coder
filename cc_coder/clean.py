"""CLEAN: drop payment thank-yous, normalize, vendor-first appears-as, sort."""

from __future__ import annotations

from typing import Iterable

from cc_coder.models import Transaction
from cc_coder.normalize import (
    extract_vendor_first,
    first_name,
    is_payment_thank_you,
    merchant_key,
    normalize_country,
    parse_amount,
    parse_date,
    title_merchant,
)


TXN_FIELDS = [
    "txn_id",
    "cardholder_raw",
    "cardholder_first",
    "txn_date",
    "post_date",
    "description_raw",
    "extended_details",
    "appears_as",
    "amount",
    "txn_type",
    "country_raw",
    "country",
    "reference_number",
    "row_class",
    "entity",
    "merchant_key",
    "gl_code",
    "gl_name",
    "coding_source",
    "confidence",
    "review_reason",
    "origin_kept",
]


def parse_raw_rows(rows: Iterable[dict[str, str]]) -> list[Transaction]:
    parsed: list[Transaction] = []
    for index, row in enumerate(rows, start=1):
        description = (row.get("Description") or "").strip()
        txn_type = (row.get("Type") or "").strip() or "Charge"
        amount = parse_amount(row.get("Amount") or "0")
        if txn_type.lower() == "credit" and amount > 0:
            amount = -amount
        if txn_type.lower() == "payment" and amount > 0:
            amount = -amount
        row_class = _row_class(txn_type, amount, description)
        appears = title_merchant(
            extract_vendor_first(description, row.get("Extended Details") or "")
        )
        txn = Transaction(
            txn_id=f"T{index:04d}",
            cardholder_raw=(row.get("Cardholder Name") or "").strip(),
            cardholder_first=first_name(row.get("Cardholder Name") or ""),
            txn_date=parse_date(row.get("Transaction Date") or ""),
            post_date=parse_date(row.get("Post Date") or row.get("Transaction Date") or ""),
            description_raw=description,
            extended_details=(row.get("Extended Details") or "").strip(),
            appears_as=appears,
            amount=amount,
            txn_type=txn_type,
            country_raw=(row.get("Country") or "").strip(),
            country=normalize_country(row.get("Country") or ""),
            reference_number=(row.get("Reference Number") or "").strip(),
            row_class=row_class,
            merchant_key=merchant_key(appears),
        )
        parsed.append(txn)
    return parsed


def drop_payment_thank_yous(
    rows: list[Transaction],
) -> tuple[list[Transaction], list[Transaction]]:
    kept: list[Transaction] = []
    dropped: list[Transaction] = []
    for row in rows:
        if is_payment_thank_you(row.description_raw, row.txn_type) or row.row_class == "PAYMENT":
            dropped.append(row)
        else:
            kept.append(row)
    return kept, dropped


def sort_charges_then_credits(rows: list[Transaction]) -> list[Transaction]:
    rank = {"CHARGE": 0, "CREDIT": 1, "PAYMENT": 2}
    return sorted(
        rows,
        key=lambda row: (
            rank.get(row.row_class, 9),
            row.txn_date,
            row.cardholder_first,
            row.txn_id,
        ),
    )


def clean_statement(raw_rows: Iterable[dict[str, str]]) -> tuple[list[Transaction], list[Transaction]]:
    parsed = parse_raw_rows(raw_rows)
    kept, dropped = drop_payment_thank_yous(parsed)
    return sort_charges_then_credits(kept), dropped


def _row_class(txn_type: str, amount: int, description: str) -> str:
    if is_payment_thank_you(description, txn_type) or txn_type.lower() == "payment":
        return "PAYMENT"
    if amount < 0 or txn_type.lower() == "credit":
        return "CREDIT"
    return "CHARGE"
