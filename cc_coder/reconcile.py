"""Reconciliation: report variance. Never force a match."""

from __future__ import annotations

from collections import defaultdict

from cc_coder.models import Reconciliation, Transaction


def build_reconciliation(
    *,
    period: str,
    reported_activity: int,
    cleaned: list[Transaction],
    dropped_payments: list[Transaction],
    review: list[Transaction],
    notes: list[str] | None = None,
) -> Reconciliation:
    cleaned_activity = sum(row.amount for row in cleaned)
    payment_amount = sum(row.amount for row in dropped_payments)
    entity_nets: dict[str, int] = defaultdict(int)
    for row in cleaned:
        entity_nets[row.entity or "UNMAPPED"] += row.amount
    entity_sum = sum(entity_nets.values())
    review_amount = sum(row.amount for row in review)
    coded_amount = cleaned_activity - review_amount
    extra = list(notes or [])
    extra.append(
        "Variance is reported, not forced. Payment thank-you rows are excluded "
        "from the coding population; issuer-reported activity may still include them."
    )
    return Reconciliation(
        period=period,
        reported_activity=reported_activity,
        cleaned_activity=cleaned_activity,
        variance_vs_statement=cleaned_activity - reported_activity,
        payment_rows_dropped=len(dropped_payments),
        payment_amount_dropped=payment_amount,
        entity_nets=dict(sorted(entity_nets.items())),
        entity_sum=entity_sum,
        variance_entities_vs_cleaned=entity_sum - cleaned_activity,
        review_count=len(review),
        review_amount=review_amount,
        coded_amount=coded_amount,
        notes=extra,
    )


def render_reconciliation_md(rec: Reconciliation, card_payable_gl: str) -> str:
    lines = [
        "# Reconciliation summary",
        "",
        f"- Period: `{rec.period}`",
        f"- Issuer-reported activity: `{rec.reported_activity}`",
        f"- Cleaned activity (thank-you payments dropped): `{rec.cleaned_activity}`",
        f"- Variance vs statement (cleaned − reported): `{rec.variance_vs_statement}`",
        f"- Payment rows dropped: `{rec.payment_rows_dropped}` (amount `{rec.payment_amount_dropped}`)",
        f"- Entity sum: `{rec.entity_sum}`",
        f"- Variance entities vs cleaned: `{rec.variance_entities_vs_cleaned}`",
        f"- Review queue: `{rec.review_count}` rows / `{rec.review_amount}` uncoded",
        f"- Coded / journal-eligible: `{rec.coded_amount}`",
        f"- Card Payable GL: `{card_payable_gl}`",
        "",
        "## Entity nets",
        "",
        "| Entity | Net |",
        "| --- | ---: |",
    ]
    for entity, net in rec.entity_nets.items():
        lines.append(f"| {entity} | {net} |")
    lines.extend(["", "## Notes", ""])
    for note in rec.notes:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)
