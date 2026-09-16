"""Orchestrate CLEAN → SPLIT → CODE → FINALIZE → JOURNAL."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from cc_coder.clean import TXN_FIELDS, clean_statement
from cc_coder.code import code_transactions, load_coa, load_reference, partition_review
from cc_coder.finalize import reference_as_rows, update_reference
from cc_coder.io_csv import read_dicts, read_json, write_dicts, write_json
from cc_coder.journal import build_journals, journal_fieldnames
from cc_coder.models import PipelineResult, Transaction
from cc_coder.reconcile import build_reconciliation, render_reconciliation_md
from cc_coder.split import apply_entity_map, entity_slug, load_entity_map

REQUIRED_FIXTURES = (
    "raw_statement.csv",
    "statement_meta.json",
    "chart_of_accounts.csv",
    "reference.csv",
    "entity_map.csv",
)


def repo_root() -> Path:
    """Directory that contains `cc_coder/` and `fixtures/` in a clone."""
    return Path(__file__).resolve().parent.parent


def resolve_fixtures_dir(raw: str | Path) -> Path:
    """Prefer the given path; if it's the default relative folder, fall back to the clone."""
    path = Path(raw)
    if path.is_dir():
        return path
    if not path.is_absolute():
        bundled = repo_root() / path
        if bundled.is_dir():
            return bundled
    return path


def missing_fixture_names(fixtures_dir: Path) -> list[str]:
    return [name for name in REQUIRED_FIXTURES if not (fixtures_dir / name).is_file()]


def require_fixtures(fixtures_dir: Path) -> None:
    if not fixtures_dir.is_dir():
        raise FileNotFoundError(
            f"fixtures directory not found: {fixtures_dir}\n"
            "Run from the repo root (the folder that contains fixtures/), "
            "or pass --fixtures PATH."
        )
    missing = missing_fixture_names(fixtures_dir)
    if missing:
        listed = "\n".join(f"  - {name}" for name in missing)
        need = ", ".join(REQUIRED_FIXTURES)
        raise FileNotFoundError(
            f"fixtures directory is missing required files: {fixtures_dir}\n"
            f"{listed}\n"
            f"Need: {need}"
        )


def run_pipeline(fixtures_dir: Path, output_dir: Path) -> PipelineResult:
    require_fixtures(fixtures_dir)
    raw = read_dicts(fixtures_dir / "raw_statement.csv")
    meta = read_json(fixtures_dir / "statement_meta.json")
    coa = load_coa(read_dicts(fixtures_dir / "chart_of_accounts.csv"))
    reference = load_reference(read_dicts(fixtures_dir / "reference.csv"))
    mapping = load_entity_map(read_dicts(fixtures_dir / "entity_map.csv"))

    payable = next((acct.gl_code for acct in coa if acct.name.lower() == "card payable"), "")
    if not payable:
        raise ValueError("dummy COA must include a Card Payable account")

    cleaned, dropped = clean_statement(raw)
    # Snapshot before split/code mutate the working rows. Origin is kept, never deleted.
    origin = [replace(row) for row in cleaned]
    tagged, by_entity, unmapped = apply_entity_map(cleaned, mapping)
    code_transactions(tagged, reference, coa)
    approved, review = partition_review(tagged)
    reference_updated = update_reference(reference, approved)
    journals = build_journals(by_entity, payable)

    extra_notes: list[str] = []
    if unmapped:
        extra_notes.append(
            f"{len(unmapped)} cleaned row(s) have no entity map; they stay on Origin "
            "and land under UNMAPPED. Totals are not force-matched."
        )

    rec = build_reconciliation(
        period=str(meta.get("period") or ""),
        reported_activity=int(meta.get("reported_activity") or 0),
        cleaned=tagged,
        dropped_payments=dropped,
        review=review,
        notes=extra_notes,
    )

    result = PipelineResult(
        cleaned=tagged,
        origin=origin,
        by_entity=by_entity,
        coded=approved,
        review=review,
        journals=journals,
        reconciliation=rec,
        reference_updated=reference_updated,
        dropped_payments=dropped,
        card_payable_gl=payable,
        unmapped=unmapped,
    )
    write_outputs(output_dir, result)
    return result


def write_outputs(output_dir: Path, result: PipelineResult) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_dicts(output_dir / "cleaned.csv", _txn_rows(result.cleaned), TXN_FIELDS)
    write_dicts(output_dir / "origin.csv", _txn_rows(result.origin), TXN_FIELDS)
    write_dicts(output_dir / "coded.csv", _txn_rows(result.coded), TXN_FIELDS)
    write_dicts(output_dir / "review_queue.csv", _txn_rows(result.review), TXN_FIELDS)
    write_dicts(
        output_dir / "dropped_payments.csv",
        _txn_rows(result.dropped_payments),
        TXN_FIELDS,
    )
    write_dicts(
        output_dir / "reference_updated.csv",
        reference_as_rows(result.reference_updated),
        ["merchant_key", "gl_code", "times_seen", "appears_as"],
    )

    split_dir = output_dir / "split"
    for entity, rows in result.by_entity.items():
        write_dicts(split_dir / f"{entity_slug(entity)}.csv", _txn_rows(rows), TXN_FIELDS)

    journals_dir = output_dir / "journals"
    for entity, journal in result.journals.items():
        write_dicts(
            journals_dir / f"{entity_slug(entity)}.csv",
            [line.as_csv_row() for line in journal.lines],
            journal_fieldnames(),
        )

    write_json(output_dir / "reconciliation.json", result.reconciliation.as_dict())
    (output_dir / "reconciliation.md").write_text(
        render_reconciliation_md(result.reconciliation, result.card_payable_gl),
        encoding="utf-8",
    )
    write_json(output_dir / "run_summary.json", _run_summary(result))


def _txn_rows(rows: list[Transaction]) -> list[dict[str, str]]:
    return [row.as_csv_row() for row in rows]


def _run_summary(result: PipelineResult) -> dict:
    return {
        "cleaned_rows": len(result.cleaned),
        "origin_rows": len(result.origin),
        "dropped_payment_rows": len(result.dropped_payments),
        "entities": sorted(result.by_entity.keys()),
        "coded_rows": len(result.coded),
        "review_rows": len(result.review),
        "journals": {
            entity: {
                "lines": len(journal.lines),
                "debit_total": journal.debit_total,
                "credit_total": journal.credit_total,
                "balanced": journal.balanced,
                "excluded_review_amount": journal.excluded_review_amount,
            }
            for entity, journal in result.journals.items()
        },
        "card_payable_gl": result.card_payable_gl,
        "unmapped_rows": len(result.unmapped),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m cc_coder",
        description=(
            "Run the synthetic multi-entity credit-card coding pipeline "
            "(clean → split → code → finalize → journal)."
        ),
    )
    parser.add_argument(
        "--fixtures",
        default="fixtures",
        help="Directory with raw_statement.csv, COA, reference, entity map, meta "
        "(cwd, then repo root)",
    )
    parser.add_argument(
        "--output",
        default="output",
        help="Directory to write journals, Origin, splits, and reconciliation",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 10):
        print(
            "Python 3.10+ is required (stdlib only — no pip install).",
            file=sys.stderr,
        )
        return 2
    args = build_parser().parse_args(argv)
    fixtures_dir = resolve_fixtures_dir(args.fixtures)
    output_dir = Path(args.output)
    try:
        result = run_pipeline(fixtures_dir, output_dir)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    rec = result.reconciliation
    print("CC Expense Coder — synthetic portfolio run")
    print(f"  cleaned rows:     {len(result.cleaned)}  (origin kept: {len(result.origin)})")
    print(f"  payments dropped: {len(result.dropped_payments)}")
    print(f"  coded / review:   {len(result.coded)} / {len(result.review)}")
    print(f"  reported:         {rec.reported_activity}")
    print(f"  cleaned activity: {rec.cleaned_activity}")
    print(f"  variance:         {rec.variance_vs_statement}  (not forced)")
    print("  journals:")
    broken = False
    for entity, journal in sorted(result.journals.items()):
        flag = "OK" if journal.balanced else "BROKEN"
        broken = broken or not journal.balanced
        print(
            f"    {entity}: debit={journal.debit_total} "
            f"credit={journal.credit_total} [{flag}]"
        )
    print(f"  wrote {output_dir}/")
    print(f"    journals:        {output_dir / 'journals'}/")
    print(f"    reconciliation:  {output_dir / 'reconciliation.md'}")
    return 1 if broken else 0
