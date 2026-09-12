"""FINALIZE: increment Reference times_seen after approved coding."""

from __future__ import annotations

from cc_coder.models import ReferenceRow, Transaction


def update_reference(
    reference: list[ReferenceRow],
    approved: list[Transaction],
) -> list[ReferenceRow]:
    """Bump times_seen for approved merchants. Add a memory row when COA coded."""
    by_key = {item.merchant_key: item for item in reference}
    for row in approved:
        if row.confidence != "confident" or not row.gl_code:
            continue
        existing = by_key.get(row.merchant_key)
        if existing:
            if existing.gl_code != row.gl_code:
                # Do not silently overwrite memory. Review belongs upstream.
                continue
            existing.times_seen += 1
            if not existing.appears_as:
                existing.appears_as = row.appears_as
        else:
            created = ReferenceRow(
                merchant_key=row.merchant_key,
                gl_code=row.gl_code,
                times_seen=1,
                appears_as=row.appears_as,
            )
            by_key[row.merchant_key] = created
    return sorted(by_key.values(), key=lambda item: item.merchant_key)


def reference_as_rows(reference: list[ReferenceRow]) -> list[dict[str, str]]:
    return [
        {
            "merchant_key": item.merchant_key,
            "gl_code": item.gl_code,
            "times_seen": str(item.times_seen),
            "appears_as": item.appears_as,
        }
        for item in reference
    ]
