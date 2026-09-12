import unittest
from pathlib import Path

from cc_coder.clean import clean_statement
from cc_coder.io_csv import read_dicts
from cc_coder.normalize import first_name, merchant_key, normalize_country, parse_amount


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class CleanTests(unittest.TestCase):
    def test_parse_whole_dollars_and_credits(self):
        self.assertEqual(parse_amount("1000"), 1000)
        self.assertEqual(parse_amount("$5,000"), 5000)
        self.assertEqual(parse_amount("(5000)"), -5000)
        self.assertEqual(parse_amount("-100000"), -100000)
        with self.assertRaises(ValueError):
            parse_amount("10.50")

    def test_country_normalizes_to_united_states(self):
        for raw in ("US", "USA", "U.S.", "U.S.A.", "usa", "United States of America"):
            self.assertEqual(normalize_country(raw), "UNITED STATES")

    def test_first_name_from_issuer_shapes(self):
        self.assertEqual(first_name("WAYNE, BRUCE"), "Bruce")
        self.assertEqual(first_name("BRUCE WAYNE"), "Bruce")
        self.assertEqual(first_name("Parker, Peter"), "Peter")
        self.assertEqual(first_name("TONY STARK"), "Tony")

    def test_merchant_key_collapses_public_variants(self):
        self.assertEqual(merchant_key("Amazon.Com"), "amazon")
        self.assertEqual(merchant_key("AMAZON MKTPLACE"), "amazon")
        self.assertEqual(merchant_key("Uber *Trip"), "uber")
        self.assertEqual(merchant_key("Starbucks Store"), "starbucks")

    def test_fixture_clean_drops_thank_you_and_sorts(self):
        cleaned, dropped = clean_statement(read_dicts(FIXTURES / "raw_statement.csv"))
        self.assertEqual(len(dropped), 1)
        self.assertIn("THANK YOU", dropped[0].description_raw.upper())
        self.assertTrue(all(row.row_class != "PAYMENT" for row in cleaned))
        self.assertTrue(all(row.country == "UNITED STATES" for row in cleaned))
        classes = [row.row_class for row in cleaned]
        last_charge = max(i for i, cls in enumerate(classes) if cls == "CHARGE")
        first_credit = min(i for i, cls in enumerate(classes) if cls == "CREDIT")
        self.assertLess(last_charge, first_credit)
        starbucks = [row for row in cleaned if row.merchant_key == "starbucks"]
        self.assertGreaterEqual(len(starbucks), 2)
        self.assertTrue(all(row.appears_as.lower().startswith("starbucks") for row in starbucks))
        self.assertEqual({row.cardholder_first for row in cleaned}, {"Bruce", "Peter", "Clark", "Diana", "Tony"})


if __name__ == "__main__":
    unittest.main()
