import json
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from cc_coder.io_csv import read_dicts
from cc_coder.pipeline import (
    REQUIRED_FIXTURES,
    main,
    resolve_fixtures_dir,
    run_pipeline,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name)
        self.result = run_pipeline(FIXTURES, self.output)

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_command_writes_journals_and_reconciliation(self):
        self.assertTrue((self.output / "reconciliation.json").is_file())
        self.assertTrue((self.output / "reconciliation.md").is_file())
        self.assertTrue((self.output / "origin.csv").is_file())
        journals = list((self.output / "journals").glob("*.csv"))
        self.assertEqual(len(journals), 3)

    def test_origin_is_kept_and_matches_cleaned(self):
        origin = read_dicts(self.output / "origin.csv")
        cleaned = read_dicts(self.output / "cleaned.csv")
        self.assertEqual(len(origin), len(cleaned))
        self.assertEqual(len(origin), len(self.result.cleaned))
        self.assertGreater(len(origin), 0)
        self.assertEqual(
            [row["txn_id"] for row in origin],
            [row["txn_id"] for row in cleaned],
        )
        # Origin is a pre-split snapshot: same rows, not mutated by split/coding.
        self.assertTrue(all(not row["entity"] for row in origin))
        self.assertTrue(all(not row["gl_code"] for row in origin))
        self.assertTrue(any(row["entity"] for row in cleaned))
        self.assertTrue(any(row["gl_code"] for row in cleaned))
        self.assertIsNot(self.result.origin[0], self.result.cleaned[0])

    def test_split_does_not_lose_rows(self):
        split_rows = 0
        for path in (self.output / "split").glob("*.csv"):
            split_rows += len(read_dicts(path))
        self.assertEqual(split_rows, len(self.result.cleaned))

    def test_variance_is_reported_not_forced(self):
        rec = self.result.reconciliation
        self.assertEqual(rec.reported_activity, 1055000)
        self.assertEqual(rec.cleaned_activity, 1155000)
        self.assertEqual(rec.variance_vs_statement, 100000)
        self.assertEqual(rec.payment_rows_dropped, 1)
        self.assertEqual(rec.variance_entities_vs_cleaned, 0)
        payload = json.loads((self.output / "reconciliation.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["variance_vs_statement"], 100000)

    def test_entity_nets(self):
        nets = self.result.reconciliation.entity_nets
        self.assertEqual(nets["Wayne Enterprises LLC"], 22000)
        self.assertEqual(nets["Daily Bugle Media LLC"], 13000)
        self.assertEqual(nets["Stark Industries Holdings"], 1120000)

    def test_uncertain_row_is_queued_not_invented(self):
        self.assertEqual(len(self.result.review), 1)
        row = self.result.review[0]
        self.assertEqual(row.merchant_key, "iron works rental")
        self.assertEqual(row.gl_code, "")
        self.assertEqual(row.amount, 1000000)
        self.assertEqual(row.confidence, "review")

    def test_codes_are_only_from_coa(self):
        allowed = {row["gl_code"] for row in read_dicts(FIXTURES / "chart_of_accounts.csv")}
        for txn in self.result.coded:
            self.assertIn(txn.gl_code, allowed)
        for journal in self.result.journals.values():
            for line in journal.lines:
                self.assertIn(line.gl_code, allowed)

    def test_reference_first_then_coa(self):
        by_source = {}
        for txn in self.result.coded:
            by_source.setdefault(txn.coding_source, []).append(txn.merchant_key)
        self.assertIn("amazon", by_source["reference"])
        self.assertIn("packet post", by_source["coa"])
        self.assertIn("city office mart", by_source["coa"])

    def test_finalize_increments_times_seen(self):
        seed = {row["merchant_key"]: int(row["times_seen"]) for row in read_dicts(FIXTURES / "reference.csv")}
        updated = {
            row["merchant_key"]: int(row["times_seen"])
            for row in read_dicts(self.output / "reference_updated.csv")
        }
        self.assertEqual(updated["amazon"], seed["amazon"] + 3)
        self.assertEqual(updated["starbucks"], seed["starbucks"] + 2)
        self.assertEqual(updated["city office mart"], 1)
        self.assertEqual(updated["packet post"], 1)
        self.assertNotIn("iron works rental", updated)

    def test_amounts_are_whole_dollars(self):
        for txn in self.result.cleaned + self.result.dropped_payments:
            self.assertIsInstance(txn.amount, int)


class CliUxTests(unittest.TestCase):
    def test_missing_fixtures_dir_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "no-such-fixtures")
            stderr = StringIO()
            with patch("sys.stderr", stderr):
                code = main(["--fixtures", missing, "--output", str(Path(tmp) / "out")])
            self.assertEqual(code, 2)
            text = stderr.getvalue()
            self.assertIn("fixtures directory not found", text)
            self.assertIn("repo root", text)
            self.assertNotIn("Traceback", text)

    def test_empty_fixtures_dir_lists_required_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "fixtures"
            empty.mkdir()
            stderr = StringIO()
            with patch("sys.stderr", stderr):
                code = main(["--fixtures", str(empty), "--output", str(Path(tmp) / "out")])
            self.assertEqual(code, 2)
            text = stderr.getvalue()
            self.assertIn("missing required files", text)
            for name in REQUIRED_FIXTURES:
                self.assertIn(name, text)
            self.assertNotIn("Traceback", text)

    def test_default_fixtures_fall_back_to_repo_when_cwd_has_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            prev = os.getcwd()
            os.chdir(tmp)
            try:
                resolved = resolve_fixtures_dir("fixtures")
            finally:
                os.chdir(prev)
        self.assertEqual(resolved.resolve(), (ROOT / "fixtures").resolve())


if __name__ == "__main__":
    unittest.main()
