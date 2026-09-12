"""JOURNAL: per-entity GL lines plus one Card Payable balancer. Debit must equal Credit."""

from __future__ import annotations

from cc_coder.models import EntityJournal, JournalLine, Transaction
from cc_coder.normalize import format_journal_date


def build_journals(
    by_entity: dict[str, list[Transaction]],
    card_payable_gl: str,
) -> dict[str, EntityJournal]:
    journals: dict[str, EntityJournal] = {}
    for entity, rows in by_entity.items():
        if entity == "UNMAPPED":
            continue
        approved = [row for row in rows if row.confidence == "confident" and row.gl_code]
        review_amt = sum(row.amount for row in rows if row.confidence == "review")
        lines = [_expense_line(row) for row in approved]
        debit_exp = sum(line.debit for line in lines)
        credit_exp = sum(line.credit for line in lines)
        net = debit_exp - credit_exp
        if net > 0:
            lines.append(
                JournalLine(
                    gl_code=card_payable_gl,
                    debit=0,
                    credit=net,
                    description="Card Payable",
                )
            )
        elif net < 0:
            lines.append(
                JournalLine(
                    gl_code=card_payable_gl,
                    debit=-net,
                    credit=0,
                    description="Card Payable",
                )
            )
        debit_total = sum(line.debit for line in lines)
        credit_total = sum(line.credit for line in lines)
        if debit_total != credit_total:
            raise AssertionError(
                f"Journal for {entity} does not balance: "
                f"debit={debit_total} credit={credit_total}"
            )
        journals[entity] = EntityJournal(
            entity=entity,
            lines=lines,
            debit_total=debit_total,
            credit_total=credit_total,
            balanced=True,
            excluded_review_amount=review_amt,
        )
    return journals


def _expense_line(row: Transaction) -> JournalLine:
    desc = f"{format_journal_date(row.txn_date)} - {row.appears_as}"
    if row.amount >= 0:
        return JournalLine(gl_code=row.gl_code, debit=row.amount, credit=0, description=desc)
    return JournalLine(gl_code=row.gl_code, debit=0, credit=-row.amount, description=desc)


def journal_fieldnames() -> list[str]:
    return ["GL Code", "Debit", "Credit", "Description"]
