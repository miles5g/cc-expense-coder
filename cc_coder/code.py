"""CODE: Reference merchant memory first, then COA keywords. Never invent GLs."""

from __future__ import annotations

from cc_coder.models import ChartAccount, ReferenceRow, Transaction


def load_coa(rows: list[dict[str, str]]) -> list[ChartAccount]:
    accounts: list[ChartAccount] = []
    for row in rows:
        keywords = [
            part.strip().lower()
            for part in (row.get("keywords") or "").split(";")
            if part.strip()
        ]
        accounts.append(
            ChartAccount(
                gl_code=(row.get("gl_code") or "").strip(),
                name=(row.get("name") or "").strip(),
                keywords=keywords,
            )
        )
    return accounts


def load_reference(rows: list[dict[str, str]]) -> list[ReferenceRow]:
    ref: list[ReferenceRow] = []
    for row in rows:
        ref.append(
            ReferenceRow(
                merchant_key=(row.get("merchant_key") or "").strip().lower(),
                gl_code=(row.get("gl_code") or "").strip(),
                times_seen=int(row.get("times_seen") or 0),
                appears_as=(row.get("appears_as") or "").strip(),
            )
        )
    return ref


def code_transactions(
    rows: list[Transaction],
    reference: list[ReferenceRow],
    coa: list[ChartAccount],
) -> list[Transaction]:
    by_code = {acct.gl_code: acct for acct in coa}
    ref_by_key = {item.merchant_key: item for item in reference}

    for row in rows:
        hit = ref_by_key.get(row.merchant_key)
        if hit:
            if hit.gl_code not in by_code:
                _flag_review(
                    row,
                    "reference_gl_not_on_coa",
                    f"Reference GL {hit.gl_code} is not on the dummy COA",
                )
                continue
            acct = by_code[hit.gl_code]
            row.gl_code = acct.gl_code
            row.gl_name = acct.name
            if hit.appears_as:
                row.appears_as = hit.appears_as
            row.coding_source = "reference"
            row.confidence = "confident"
            row.review_reason = ""
            continue

        matches = _coa_keyword_matches(row.merchant_key, row.appears_as, coa)
        if len(matches) == 1:
            acct = matches[0]
            row.gl_code = acct.gl_code
            row.gl_name = acct.name
            row.coding_source = "coa"
            row.confidence = "confident"
            row.review_reason = ""
            continue
        if len(matches) > 1:
            codes = ", ".join(acct.gl_code for acct in matches)
            _flag_review(row, "ambiguous_coa", f"Multiple COA keyword hits: {codes}")
            continue
        _flag_review(row, "no_gl", "No Reference memory or COA keyword match")
    return rows


def _coa_keyword_matches(
    key: str, appears_as: str, coa: list[ChartAccount]
) -> list[ChartAccount]:
    haystack = f"{key} {appears_as}".lower()
    hits: list[ChartAccount] = []
    for acct in coa:
        if not acct.keywords:
            continue
        if any(_contains_keyword(haystack, word) for word in acct.keywords):
            hits.append(acct)
    return hits


def _contains_keyword(haystack: str, keyword: str) -> bool:
    return f" {keyword} " in f" {haystack} "


def _flag_review(row: Transaction, source: str, reason: str) -> None:
    row.gl_code = ""
    row.gl_name = ""
    row.coding_source = source
    row.confidence = "review"
    row.review_reason = reason


def partition_review(
    rows: list[Transaction],
) -> tuple[list[Transaction], list[Transaction]]:
    coded = [row for row in rows if row.confidence == "confident" and row.gl_code]
    review = [row for row in rows if not (row.confidence == "confident" and row.gl_code)]
    return coded, review
