import json
import unittest

from cc_coder.llm import CONFIDENCE_FLOOR, parse_suggestion, suggest_for_review
from cc_coder.models import ChartAccount, Transaction


def _row() -> Transaction:
    return Transaction(
        txn_id="T1", cardholder_raw="TONY STARK", cardholder_first="Tony", txn_date="2026-03-26",
        post_date="2026-03-27", description_raw="IRON WORKS RENTAL", extended_details="BAY 7",
        appears_as="Iron Works Rental", amount=1000000, txn_type="Charge", country_raw="US",
        country="UNITED STATES", reference_number="REF1", row_class="CHARGE",
        entity="Stark Industries Holdings", merchant_key="iron works rental",
        coding_source="no_gl", confidence="review", review_reason="No match",
    )


COA = [ChartAccount("2100", "Card Payable"), ChartAccount("5600", "Equipment Rental")]


def _reply(gl, confidence):
    return lambda _prompt: json.dumps({"gl_code": gl, "confidence": confidence, "reason": "rental"})


class LlmStepTests(unittest.TestCase):
    def test_confident_valid_code_is_coded(self):
        row = _row()
        summary = suggest_for_review([row], COA, [], caller=_reply("5600", 0.95))
        self.assertEqual((row.gl_code, row.coding_source, row.confidence), ("5600", "llm", "confident"))
        self.assertEqual(summary.coded, 1)

    def test_invented_code_stays_in_review(self):
        row = _row()
        suggest_for_review([row], COA, [], caller=_reply("9999", 0.99))
        self.assertEqual((row.gl_code, row.confidence), ("", "review"))

    def test_card_payable_is_never_a_valid_answer(self):
        row = _row()
        suggest_for_review([row], COA, [], caller=_reply("2100", 0.99))
        self.assertEqual(row.confidence, "review")

    def test_low_confidence_stays_in_review_with_suggestion(self):
        row = _row()
        suggest_for_review([row], COA, [], caller=_reply("5600", CONFIDENCE_FLOOR - 0.1))
        self.assertEqual(row.confidence, "review")
        self.assertIn("LLM suggests 5600", row.review_reason)

    def test_failed_call_keeps_row_for_human(self):
        def boom(_prompt):
            raise TimeoutError
        row = _row()
        summary = suggest_for_review([row], COA, [], caller=boom)
        self.assertEqual((row.confidence, summary.errors), ("review", 1))

    def test_parse_handles_prose_around_json(self):
        text = 'Sure: {"gl_code": "5600", "confidence": 0.9, "reason": "x"}'
        self.assertEqual(parse_suggestion(text, {"5600"})[0], "5600")
        self.assertIsNone(parse_suggestion("no json here", {"5600"}))


if __name__ == "__main__":
    unittest.main()
