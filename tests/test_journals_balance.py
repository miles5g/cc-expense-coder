import tempfile
import unittest
from pathlib import Path

from cc_coder.io_csv import read_dicts
from cc_coder.journal import journal_fieldnames
from cc_coder.pipeline import run_pipeline


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def _money(value: str) -> int:
    return int(value) if value else 0


class JournalBalanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name)
        self.result = run_pipeline(FIXTURES, self.output)

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_entity_journal_balances(self):
        for entity, journal in self.result.journals.items():
            self.assertTrue(journal.balanced, entity)
            self.assertEqual(journal.debit_total, journal.credit_total, entity)
            self.assertGreater(journal.debit_total, 0, entity)

    def test_journal_files_have_required_columns_and_balance(self):
        for path in (self.output / "journals").glob("*.csv"):
            rows = read_dicts(path)
            self.assertGreaterEqual(len(rows), 2, path.name)
            self.assertEqual(list(rows[0].keys()), journal_fieldnames())
            debit = sum(_money(row["Debit"]) for row in rows)
            credit = sum(_money(row["Credit"]) for row in rows)
            self.assertEqual(debit, credit, path.name)
            payable = [row for row in rows if row["Description"] == "Card Payable"]
            self.assertEqual(len(payable), 1, path.name)
            self.assertEqual(payable[0]["GL Code"], "2100")

    def test_positive_is_debit_negative_is_credit(self):
        stark = self.result.journals["Stark Industries Holdings"]
        amazon_refund = [
            line
            for line in stark.lines
            if line.credit == 5000 and line.description.endswith(" - Amazon")
        ]
        self.assertEqual(len(amazon_refund), 1)
        self.assertEqual(amazon_refund[0].debit, 0)
        amazon_charge = [
            line
            for line in stark.lines
            if line.debit == 100000 and line.description.endswith(" - Amazon")
        ]
        self.assertEqual(len(amazon_charge), 1)

    def test_description_uses_short_date_and_appears_as(self):
        wayne = self.result.journals["Wayne Enterprises LLC"]
        expense = [line for line in wayne.lines if line.description != "Card Payable"]
        self.assertTrue(expense)
        for line in expense:
            prefix, _, appears = line.description.partition(" - ")
            self.assertRegex(prefix, r"^\d{2}/\d{2}/\d{2}$")
            self.assertTrue(appears)

    def test_review_amount_is_excluded_from_journals(self):
        stark = self.result.journals["Stark Industries Holdings"]
        self.assertEqual(stark.excluded_review_amount, 1000000)
        self.assertEqual(stark.debit_total, 125000)
        self.assertEqual(stark.credit_total, 125000)


if __name__ == "__main__":
    unittest.main()
